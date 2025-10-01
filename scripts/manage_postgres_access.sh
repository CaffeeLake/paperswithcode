#!/bin/bash

# PostgreSQL Access Management Script
# This script helps manage IP whitelisting for PostgreSQL access

PG_HBA_FILE="/etc/postgresql/16/main/pg_hba.conf"
BACKUP_DIR="/etc/postgresql/16/main/backups"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Function to create backup
create_backup() {
    local timestamp=$(date +"%Y%m%d_%H%M%S")
    cp "$PG_HBA_FILE" "$BACKUP_DIR/pg_hba.conf.backup.$timestamp"
    echo "Backup created: $BACKUP_DIR/pg_hba.conf.backup.$timestamp"
}

# Function to add IP to whitelist
add_ip() {
    local ip="$1"
    local user="$2"
    local database="$3"

    if [[ -z "$ip" || -z "$user" || -z "$database" ]]; then
        echo "Usage: $0 add <IP_ADDRESS> <USERNAME> <DATABASE>"
        echo "Example: $0 add 192.168.1.100 paperswithcode_user paperswithcode"
        exit 1
    fi

    # Validate IP address
    if ! [[ $ip =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
        echo "Error: Invalid IP address format"
        exit 1
    fi

    create_backup

    # Add the IP to pg_hba.conf
    echo "host    $database    $user    $ip/32    md5" >> "$PG_HBA_FILE"

    echo "Added IP $ip for user $user to database $database"
    echo "Reloading PostgreSQL configuration..."
    sudo systemctl reload postgresql

    echo "Configuration updated successfully!"
}

# Function to remove IP from whitelist
remove_ip() {
    local ip="$1"

    if [[ -z "$ip" ]]; then
        echo "Usage: $0 remove <IP_ADDRESS>"
        exit 1
    fi

    create_backup

    # Remove lines containing the IP
    sed -i "/$ip\/32/d" "$PG_HBA_FILE"

    echo "Removed IP $ip from whitelist"
    echo "Reloading PostgreSQL configuration..."
    sudo systemctl reload postgresql

    echo "Configuration updated successfully!"
}

# Function to list current whitelisted IPs
list_ips() {
    echo "Current PostgreSQL access rules:"
    echo "================================"
    grep -E "host.*md5" "$PG_HBA_FILE" | grep -v "127.0.0.1\|::1" || echo "No external IPs whitelisted"
}

# Function to show help
show_help() {
    echo "PostgreSQL Access Management Script"
    echo "==================================="
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  add <IP> <USER> <DATABASE>  - Add IP to whitelist"
    echo "  remove <IP>                 - Remove IP from whitelist"
    echo "  list                        - List current whitelisted IPs"
    echo "  backup                      - Create backup of current config"
    echo "  help                        - Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 add 192.168.1.100 paperswithcode_user paperswithcode"
    echo "  $0 remove 192.168.1.100"
    echo "  $0 list"
    echo ""
    echo "Security Notes:"
    echo "- Only add IPs you trust"
    echo "- Use /32 for single IP addresses"
    echo "- Changes require PostgreSQL reload"
    echo "- Backups are automatically created"
}

# Main script logic
case "$1" in
    "add")
        add_ip "$2" "$3" "$4"
        ;;
    "remove")
        remove_ip "$2"
        ;;
    "list")
        list_ips
        ;;
    "backup")
        create_backup
        ;;
    "help"|"--help"|"-h"|"")
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
