#!/bin/bash

# Plane Project Setup Script
# This script prepares the local development environment by setting up all necessary .env files
# https://github.com/makeplane/plane

# Set colors for output messages
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Print header
echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${BLUE}                   Plane - Project Management Tool                    ${NC}"
echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}Setting up your development environment...${NC}\n"

# Function to handle file copying with error checking
copy_env_file() {
    local source=$1
    local destination=$2

    if [ ! -f "$source" ]; then
        echo -e "${RED}Error: Source file $source does not exist.${NC}"
        return 1
    fi

    if [ -f "$destination" ]; then
        echo -e "${YELLOW}•${NC} Preserved existing $destination"
        return 0
    fi

    if cp "$source" "$destination"; then
        echo -e "${GREEN}✓${NC} Copied $destination"
    else
        echo -e "${RED}✗${NC} Failed to copy $destination"
        return 1
    fi
}

# Generate the local-only runtime authentication secret when the untracked
# Compose secret file is absent. The value is never written to a tracked
# example or passed as a child-process environment variable.
ensure_agent_runtime_secret() {
    local runtime_secret temporary

    if [ -s ".plane-agent-runtime.secret" ] \
        && [ "$(wc -l < .plane-agent-runtime.secret | tr -d ' ')" -eq 0 ] \
        && [ "$(wc -c < .plane-agent-runtime.secret | tr -d ' ')" -ge 32 ]; then
        echo -e "${YELLOW}•${NC} Preserved existing .plane-agent-runtime.secret"
    else
        runtime_secret=$(tr -dc 'A-Za-z0-9' < /dev/urandom | head -c48)
        if [ -z "$runtime_secret" ]; then
            echo -e "${RED}Error: Failed to generate the local Agent runtime secret.${NC}"
            return 1
        fi

        umask 077
        temporary=$(mktemp ".plane-agent-runtime.secret.tmp.XXXXXX")
        if printf '%s' "$runtime_secret" > "$temporary" && mv "$temporary" .plane-agent-runtime.secret; then
            echo -e "${GREEN}✓${NC} Generated .plane-agent-runtime.secret"
        else
            rm -f "$temporary"
            echo -e "${RED}✗${NC} Failed to create .plane-agent-runtime.secret${NC}"
            return 1
        fi
    fi

    # Migrate an older ignored .env value out of the process environment so
    # the Compose secret always comes from the mounted file seam.
    if grep -q '^PLANE_AGENT_RUNTIME_SECRET=' .env; then
        temporary=$(mktemp)
        if awk '$1 != "PLANE_AGENT_RUNTIME_SECRET=" && $0 !~ /^PLANE_AGENT_RUNTIME_SECRET=/' .env > "$temporary" && mv "$temporary" .env; then
            echo -e "${GREEN}✓${NC} Removed legacy .env Agent runtime secret"
        else
            rm -f "$temporary"
            echo -e "${RED}✗${NC} Failed to remove the legacy .env Agent runtime secret${NC}"
            return 1
        fi
    fi
}

# Export character encoding settings for macOS compatibility
export LC_ALL=C
export LC_CTYPE=C
echo -e "${YELLOW}Setting up environment files...${NC}"

# Copy all environment example files
services=("" "web" "api" "space" "admin" "live")
success=true

for service in "${services[@]}"; do
    if [ "$service" == "" ]; then
        # Handle root .env file
        prefix="./"
    else
        # Handle service .env files in apps folder
        prefix="./apps/$service/"
    fi

    copy_env_file "${prefix}.env.example" "${prefix}.env" || success=false
done

ensure_agent_runtime_secret || success=false

# Generate SECRET_KEY for Django when it is not already configured
if [ -f "./apps/api/.env" ]; then
    if grep -q '^SECRET_KEY=' ./apps/api/.env; then
        echo -e "${YELLOW}•${NC} Preserved existing apps/api/.env SECRET_KEY"
    else
        echo -e "\n${YELLOW}Generating Django SECRET_KEY...${NC}"
        SECRET_KEY=$(tr -dc 'a-z0-9' < /dev/urandom | head -c50)

        if [ -z "$SECRET_KEY" ]; then
            echo -e "${RED}Error: Failed to generate SECRET_KEY.${NC}"
            echo -e "${RED}Ensure 'tr' and 'head' commands are available on your system.${NC}"
            success=false
        else
            echo -e "SECRET_KEY=\"$SECRET_KEY\"" >> ./apps/api/.env
            echo -e "${GREEN}✓${NC} Added SECRET_KEY to apps/api/.env"
        fi
    fi
else
    echo -e "${RED}✗${NC} apps/api/.env not found. SECRET_KEY not added."
    success=false
fi

# Verify that local env examples, Docker networking, and proxy routes agree.
./tools/check-local-dev.sh || success=false

# Use an existing pnpm installation, or activate the packageManager version through Corepack.
if ! command -v pnpm >/dev/null 2>&1; then
    if command -v corepack >/dev/null 2>&1; then
        corepack enable pnpm || success=false
    else
        echo -e "${RED}✗${NC} pnpm is not installed and Corepack is unavailable."
        success=false
    fi
fi

# Install Node dependencies when pnpm is available.
if command -v pnpm >/dev/null 2>&1; then
    pnpm install || success=false
fi

# Summary
echo -e "\n${YELLOW}Setup status:${NC}"
if [ "$success" = true ]; then
    echo -e "${GREEN}✓${NC} Environment setup completed successfully!\n"
    echo -e "${BOLD}Next steps:${NC}"
    echo -e "1. Review the .env files in each folder if needed"
    echo -e "2. Start the services with: ${BOLD}docker compose -f docker-compose-local.yml up -d${NC}"
    echo -e "3. Start all development apps with: ${BOLD}pnpm dev${NC}"
    echo -e "\n${GREEN}Happy coding! 🚀${NC}"
else
    echo -e "${RED}✗${NC} Some issues occurred during setup. Please check the errors above.\n"
    echo -e "For help, visit: ${BLUE}https://github.com/makeplane/plane${NC}"
    exit 1
fi
