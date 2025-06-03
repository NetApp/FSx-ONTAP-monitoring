#!/bin/bash

INPUT_FILE="input.txt"
HARVEST_FILE="harvest.yml"
HARVEST_COMPOSE_FILE="harvest-compose.yml"
DISCOVERY_FILE="yace-config.yaml"
TARGETS_FILE="/opt/harvest/container/prometheus/harvest_targets.yml"  # File for targets
BASE_PORT=12990  # Starting port number for the first cluster

# Check for required tools
check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo "ERROR: $1 is not installed."
        return 1
    fi
    return 0
}

# Check for yq
if ! check_command yq; then
    echo "INFO: yq is not installed. Installing ... "
    wget https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 -O /usr/local/bin/yq
    sudo chmod +x /usr/local/bin/yq
fi

# Check for AWS CLI
if ! check_command aws; then
    echo "ERROR: AWS CLI is not installed. Please install it first."
    exit 1
fi

# Ensure required files exist
for file in "$HARVEST_FILE" "$HARVEST_COMPOSE_FILE" "$DISCOVERY_FILE"; do
    if [[ ! -f "$file" ]]; then
        echo "Error: $file not found."
        exit 1
    fi
done

# Create targets directory if it doesn't exist
TARGETS_DIR=$(dirname "$TARGETS_FILE")
if [[ ! -d "$TARGETS_DIR" ]]; then
    echo "Creating targets directory: $TARGETS_DIR"
    mkdir -p "$TARGETS_DIR"
fi

# Validate input file exists
if [[ ! -f "$INPUT_FILE" ]]; then
    echo "Error: Input file $INPUT_FILE not found."
    exit 1
fi

# Validate input file format and extract regions for YACE
echo "Validating input file and extracting regions for YACE..."
LINE_NUM=0
INPUT_CLUSTERS=()
INVALID_LINES=0
UNIQUE_REGIONS=()

# Expecting: cluster_name,cluster_ip,secret_arn,region
while IFS=', ' read -r cluster_name cluster_ip secret_arn region; do
    LINE_NUM=$((LINE_NUM + 1))

    # Skip empty lines and lines that start with a '#'
    if [[ "${cluster_name}" == \#* || ( -z "$cluster_name" && -z "$cluster_ip" && -z "$secret_arn" && -z "$region" ) ]]; then
        continue
    fi

    # Validate all fields are present
    if [[ -z "$cluster_name" || -z "$cluster_ip" || -z "$secret_arn" || -z "$region" ]]; then
        echo "ERROR: Line $LINE_NUM has missing fields: $cluster_name,$cluster_ip,$secret_arn,$region"
        INVALID_LINES=$((INVALID_LINES + 1))
        continue
    fi

    # Validate cluster_ip format (basic IP or hostname validation)
    if ! [[ "$cluster_ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ || "$cluster_ip" =~ ^[a-zA-Z0-9][a-zA-Z0-9\.-]+$ ]]; then
        echo "ERROR: Line $LINE_NUM has invalid IP or hostname format: $cluster_ip"
        INVALID_LINES=$((INVALID_LINES + 1))
        continue
    fi

    # Validate secret_arn format
    if ! [[ "$secret_arn" =~ ^arn:aws:secretsmanager:[a-z0-9-]+:[0-9]+:secret:.+$ ]]; then
        echo "ERROR: Line $LINE_NUM has invalid secret ARN format: $secret_arn"
        INVALID_LINES=$((INVALID_LINES + 1))
        continue
    fi

    # Only add region if not already in UNIQUE_REGIONS
    is_unique=true
    for r in "${UNIQUE_REGIONS[@]}"; do
        if [[ "$r" == "$region" ]]; then
            is_unique=false
            break
        fi
    done
    if [[ -n "$region" && "$is_unique" == true ]]; then
        UNIQUE_REGIONS+=("$region")
    fi

    # Add to array
    INPUT_CLUSTERS+=("$cluster_name|$cluster_ip|$secret_arn|$region")

    echo "✓ Line $LINE_NUM validated successfully"

done < "$INPUT_FILE"

# Exit if there are any invalid lines
if [[ $INVALID_LINES -gt 0 ]]; then
    echo "ERROR: Found $INVALID_LINES invalid entries in $INPUT_FILE. Please fix before continuing."
    exit 1
fi

# Exit if no valid entries found
if [[ ${#INPUT_CLUSTERS[@]} -eq 0 ]]; then
    echo "ERROR: No valid clusters found in $INPUT_FILE."
    exit 1
fi

echo "Input validation complete. Found ${#INPUT_CLUSTERS[@]} valid clusters."

# Process harvest.yml
echo "Updating $HARVEST_FILE..."
for entry in "${INPUT_CLUSTERS[@]}"; do
    IFS='|' read -r cluster_name cluster_ip secret_arn region <<< "$entry"

    # Check if Poller exists
    if yq e ".Pollers.$cluster_name" "$HARVEST_FILE" | grep -q 'null'; then
        # Add new poller
        yq -i -I 5 ".Pollers.$cluster_name = {
          \"datacenter\": \"fsx\",
          \"addr\": \"$cluster_ip\",
          \"collectors\": [\"Rest\", \"RestPerf\", \"Ems\"],
          \"exporters\": [\"prometheus1\"],
          \"credentials_script\": {
            \"path\": \"/opt/fetch-credentails\",
            \"schedule\": \"3h\",
            \"timeout\": \"10s\"
          }
        }" "$HARVEST_FILE"
        echo "Added new poller: $cluster_name to $HARVEST_FILE"
    else
        # Update only the addr field
        yq -i ".Pollers.$cluster_name.addr = \"$cluster_ip\"" "$HARVEST_FILE"
        echo "Updated addr for poller: $cluster_name in $HARVEST_FILE"
    fi
done

# Remove blocks from harvest.yml that are not in input.txt
EXISTING_CLUSTERS=$(yq e '.Pollers | keys' "$HARVEST_FILE" | sed 's/- //g')
for cluster_name in $EXISTING_CLUSTERS; do
    if ! printf '%s\n' "${INPUT_CLUSTERS[@]}" | grep -q "^$cluster_name|"; then
        yq -i "del(.Pollers.$cluster_name)" "$HARVEST_FILE"
        echo "Removed poller: $cluster_name from $HARVEST_FILE"
    fi
done

# Load existing ports from harvest-compose.yml to preserve them
declare -A CLUSTER_PORTS
if [[ -f "$HARVEST_COMPOSE_FILE" ]]; then
    echo "DEBUG: Loading existing ports from $HARVEST_COMPOSE_FILE"
    # Extract cluster_name and port from existing compose file
    while IFS= read -r line; do
        cluster=$(echo "$line" | awk '{print $1}')
        port=$(echo "$line" | awk '{print $2}' | cut -d':' -f1)
        if [[ -n "$cluster" && -n "$port" ]]; then
            CLUSTER_PORTS["$cluster"]="$port"
            echo "DEBUG: Existing port - $cluster => $port"
        fi
    done < <(yq e '.services | to_entries | .[] | select(.key != "yace") | "\(.key) \(.value.ports[0])"' "$HARVEST_COMPOSE_FILE")
fi

# Find the next available port
find_next_port() {
    local port=$BASE_PORT
    while :; do
        local used=false
        for p in "${CLUSTER_PORTS[@]}"; do
            if [[ "$p" == "$port" ]]; then
                used=true
                break
            fi
        done
        if [[ "$used" == false ]]; then
            echo "$port"
            return
        fi
        port=$((port + 1))
    done
}

# Process harvest-compose.yml with dynamic ports (preserve existing ports)
echo "Updating $HARVEST_COMPOSE_FILE..."
TARGETS=()
for entry in "${INPUT_CLUSTERS[@]}"; do
    IFS='|' read -r cluster_name cluster_ip secret_arn region <<< "$entry"

    # Use existing port if present, otherwise assign next available
    if [[ -n "${CLUSTER_PORTS[$cluster_name]}" ]]; then
        current_port="${CLUSTER_PORTS[$cluster_name]}"
        echo "DEBUG: Keeping existing port for $cluster_name: $current_port"
    else
        current_port=$(find_next_port)
        CLUSTER_PORTS["$cluster_name"]="$current_port"
        echo "DEBUG: Recycling/assigning new port for $cluster_name: $current_port"
    fi

    # Check if service exists
    if yq e ".services.$cluster_name" "$HARVEST_COMPOSE_FILE" | grep -q 'null'; then
        # Add new service with dynamic port
        yq -i -I 5 ".services.$cluster_name = {
          \"image\": \"ghcr.io/tlvdevops/harvest-fsx:latest\",
          \"container_name\": \"poller-$cluster_name\",
          \"restart\": \"unless-stopped\",
          \"ports\": [\"$current_port:$current_port\"],
          \"command\": \"--poller $cluster_name --promPort $current_port --config /opt/harvest.yml\",
          \"volumes\": [
            \"./cert:/opt/harvest/cert\",
            \"./harvest.yml:/opt/harvest.yml\",
            \"./conf:/opt/harvest/conf\"
          ],
          \"environment\": [
            \"SECRET_ARN=$secret_arn\"
          ],
          \"networks\": [\"backend\"]
        }" "$HARVEST_COMPOSE_FILE"
        echo "Added new service: $cluster_name with port $current_port to $HARVEST_COMPOSE_FILE"
    else
        # Update only the environment variables and dynamic port
        yq -i ".services.$cluster_name.environment[0] = \"SECRET_ARN=$secret_arn\"" "$HARVEST_COMPOSE_FILE"
        yq -i ".services.$cluster_name.ports[0] = \"$current_port:$current_port\"" "$HARVEST_COMPOSE_FILE"
        yq -i ".services.$cluster_name.command = \"--poller $cluster_name --promPort $current_port --config /opt/harvest.yml\"" "$HARVEST_COMPOSE_FILE"
        echo "Updated service: $cluster_name with port $current_port in $HARVEST_COMPOSE_FILE"
    fi

    # Add to targets array without quotes
    TARGETS+=("$cluster_name:$current_port")
done

## Remove blocks from harvest-compose.yml that are not in input.txt
EXISTING_SERVICES=$(yq e '.services | keys' "$HARVEST_COMPOSE_FILE" | sed 's/- //g')
for cluster_name in $EXISTING_SERVICES; do
    if [[ "$cluster_name" == "yace" ]]; then
        continue  # Skip removal for 'yace' service
    fi
    if ! printf '%s\n' "${INPUT_CLUSTERS[@]}" | grep -q "^$cluster_name|"; then
        yq -i "del(.services.$cluster_name)" "$HARVEST_COMPOSE_FILE"
        echo "Removed service: $cluster_name from $HARVEST_COMPOSE_FILE"
    fi
done

# Update yace-config.yaml with unique regions
if [[ ${#UNIQUE_REGIONS[@]} -gt 0 ]]; then
    yq -i ".discovery.jobs[0].regions = [$(printf '"%s",' "${UNIQUE_REGIONS[@]}" | sed 's/,$//')]" "$DISCOVERY_FILE"
    echo "Updated regions in $DISCOVERY_FILE: ${UNIQUE_REGIONS[*]}"
else
    yq -i "del(.discovery.jobs[0].regions)" "$DISCOVERY_FILE"
    echo "Removed regions from $DISCOVERY_FILE as no regions are present in input.txt"
fi

# Update harvest_targets.yml with targets
echo "Updating $TARGETS_FILE..."
if [[ ${#TARGETS[@]} -gt 0 ]]; then
    # Format the targets array as a valid YAML list
    formatted_targets=$(printf -- "- '%s'\n" "${TARGETS[@]}" | sed "s/^/  /")
    echo "- targets:
$formatted_targets" > "$TARGETS_FILE"
    echo "Updated targets in $TARGETS_FILE"
else
    # Create an empty list if no targets are present
    echo "- targets: []" > "$TARGETS_FILE"
    echo "Created empty targets list in $TARGETS_FILE as no clusters are present in input.txt"
fi

echo "Restarting containers..."
docker-compose -f prom-stack.yml -f harvest-compose.yml down

docker-compose -f prom-stack.yml -f harvest-compose.yml up -d --remove-orphans

echo "✅ All files have been updated successfully."
echo "✅ Service configurations updated for ${#INPUT_CLUSTERS[@]} clusters."
