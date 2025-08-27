#!/bin/bash

# LichOSCLI Command Test Script
# This script tests all possible command invocations from possible-commands.md
# If any command fails, it exits and reports which command failed
#
# Usage:
#   ./test-all-commands.sh [all|<test-group>...]
#   
# Examp    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP --branch $TEST_BRANCH create testpackage" "Create with full host options"
#   ./test-all-commands.sh basic mr               # Run only basic and mr tests
#   ./test-all-commands.sh clone                  # Run only clone tests
#   ./test-all-commands.sh                        # Run default test groups (basic, getartifacts)

set -e  

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' 


TEST_PACKAGE="lichoscli"
TEST_HOST="gitlab.example.com"
TEST_PKG_GROUP="your-group/platform-os/pkg"
TEST_BRANCH="flocken"


CLI_CMD="./cli"

# Control output verbosity
SHOW_OUTPUT_LINES=40  # Number of lines to show from output
QUIET_MODE=false      # Set to true to only show errors

test_count=0
passed_count=0

ALL_TEST_GROUPS=(
    "basic"          
    "browse"         
    # "build"          
    # "clone"          
    # "create"         
    "disable"        
    "enable"         
    "getartifacts"   
    "list"           
    "log"            
    "mr"             
    # "pdiff"          
    "show"           
    "status"         
    # "trigger"        
    "workspace"      
)

# Default test groups (when no arguments provided)
DEFAULT_TEST_GROUPS=(
    "basic"          
    "getartifacts"
    "log"
    "status"
    "list"
    "show"
      
)

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS] [all|<test-group>...]"
    echo ""
    echo "Options:"
    echo "  --quiet                   # Only show errors, no output for passing tests"
    echo "  --lines N                 # Show N lines of output instead of default 40"
    echo "  -h, --help                # Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 all                    # Run all tests"
    echo "  $0 basic mr               # Run only basic and mr tests"
    echo "  $0 clone                  # Run only clone tests"
    echo "  $0 --quiet log            # Run log tests showing only errors"
    echo "  $0 --lines 10 log         # Run log tests showing last 10 lines"
    echo "  $0                        # Run default test groups (basic, getartifacts)"
    echo ""
    echo "Available test groups:"
    printf "  %s\n" "${ALL_TEST_GROUPS[@]}"
}

# Function to validate test group
is_valid_test_group() {
    local group="$1"
    for valid_group in "${ALL_TEST_GROUPS[@]}"; do
        if [[ "$valid_group" == "$group" ]]; then
            return 0
        fi
    done
    return 1
}

# Parse command line arguments
TEST_GROUPS=()
while [[ $# -gt 0 ]]; do
    case $1 in
        --quiet)
            QUIET_MODE=true
            shift
            ;;
        --lines)
            if [[ -n "$2" && "$2" =~ ^[0-9]+$ ]]; then
                SHOW_OUTPUT_LINES="$2"
                shift 2
            else
                echo -e "${RED}Error: --lines requires a numeric argument${NC}"
                show_usage
                exit 1
            fi
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        all)
            TEST_GROUPS=("${ALL_TEST_GROUPS[@]}")
            shift
            ;;
        *)
            if is_valid_test_group "$1"; then
                TEST_GROUPS+=("$1")
                shift
            else
                echo -e "${RED}Error: Invalid test group '$1'${NC}"
                echo ""
                show_usage
                exit 1
            fi
            ;;
    esac
done

# If no test groups specified, use defaults
if [[ ${#TEST_GROUPS[@]} -eq 0 ]]; then
    TEST_GROUPS=("${DEFAULT_TEST_GROUPS[@]}")
fi

run_test() {
    local cmd="$1"
    local description="$2"
    
    test_count=$((test_count + 1))
    echo -e "${YELLOW}[Test $test_count]${NC} Testing: $description"
    echo -e "${YELLOW}Command:${NC} $cmd"
    
    # Create temporary files for stdout and stderr
    local stdout_file=$(mktemp)
    local stderr_file=$(mktemp)
    
    # Run command and capture output
    if eval "$cmd" > "$stdout_file" 2> "$stderr_file"; then
        echo -e "${GREEN}✓ PASSED${NC}"
        passed_count=$((passed_count + 1))
        
        # Show output only if not in quiet mode
        if [[ "$QUIET_MODE" == "false" ]]; then
            local line_count=$(wc -l < "$stdout_file")
            if [[ $line_count -gt $SHOW_OUTPUT_LINES ]]; then
                echo -e "${BLUE}Output (last $SHOW_OUTPUT_LINES lines):${NC}"
                tail -n "$SHOW_OUTPUT_LINES" "$stdout_file"
            elif [[ $line_count -gt 0 ]]; then
                echo -e "${BLUE}Output:${NC}"
                cat "$stdout_file"
            fi
        fi
        echo ""
    else
        local exit_code=$?
        echo -e "${RED}✗ FAILED${NC} Command failed with exit code: $exit_code"
        echo -e "${RED}Failed command:${NC} $cmd"
        echo -e "${RED}Description:${NC} $description"
        
        # Show stderr if present
        if [[ -s "$stderr_file" ]]; then
            echo -e "${RED}Error output:${NC}"
            cat "$stderr_file"
        fi
        
        # Show last lines of stdout if present
        if [[ -s "$stdout_file" ]]; then
            local line_count=$(wc -l < "$stdout_file")
            if [[ $line_count -gt $SHOW_OUTPUT_LINES ]]; then
                echo -e "${RED}Output (last $SHOW_OUTPUT_LINES lines):${NC}"
                tail -n "$SHOW_OUTPUT_LINES" "$stdout_file"
            else
                echo -e "${RED}Output:${NC}"
                cat "$stdout_file"
            fi
        fi
        
        # Clean up temp files
        rm -f "$stdout_file" "$stderr_file"
        exit $exit_code
    fi
    
    # Clean up temp files
    rm -f "$stdout_file" "$stderr_file"
}


print_test_header() {
    local group_name="$1"
    echo "=========================================="
    echo "Testing $group_name"
    echo "=========================================="
}


test_basic() {
    print_test_header "Basic Commands"
    
    run_test "$CLI_CMD --version" "Version check"
    run_test "$CLI_CMD --help" "Help command"
}


test_browse() {
    print_test_header "Browse Command"

    run_test "$CLI_CMD browse" "Browse (auto-detect)"
    run_test "$CLI_CMD browse ." "Browse current directory"
    run_test "$CLI_CMD browse $TEST_PACKAGE" "Browse package"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP browse $TEST_PACKAGE" "Browse with full options"
    
}


test_build() {
    print_test_header "Build Command"

    
    run_test "$CLI_CMD build" "Build (auto-detect)"
    run_test "$CLI_CMD build ." "Build current directory"
    run_test "$CLI_CMD build $TEST_PACKAGE" "Build package"
    run_test "$CLI_CMD build --architecture amd64" "Build with amd64 architecture"
    run_test "$CLI_CMD build --architecture arm64" "Build with arm64 architecture"
    run_test "$CLI_CMD build $TEST_PACKAGE --architecture amd64" "Build package with amd64 architecture"
    run_test "$CLI_CMD build " "Build with shell option"
    run_test "$CLI_CMD build $TEST_PACKAGE " "Build package with shell option"
    run_test "$CLI_CMD build --enable-cross" "Build with cross compilation"
    run_test "$CLI_CMD build $TEST_PACKAGE --enable-cross" "Build package with cross compilation"
    run_test "$CLI_CMD build --profile cross" "Build with cross profile"
    run_test "$CLI_CMD build --network bridge" "Build with bridge network"
    run_test "$CLI_CMD build $TEST_PACKAGE --profile cross --network bridge" "Build package with profile and network"    
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP build $TEST_PACKAGE --architecture amd64" "Build with full host options"
}


test_clone() {
    print_test_header "Clone Command"

    if [[ -d "$TEST_PACKAGE" ]]; then
        rm -rf "$TEST_PACKAGE"
    fi
    
    run_test "$CLI_CMD clone $TEST_PACKAGE" "Clone package"
    
    if [[ -d "$TEST_PACKAGE" ]]; then
        rm -rf "$TEST_PACKAGE"
    fi
    
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP clone $TEST_PACKAGE" "Clone with full options"
    
    if [[ -d "$TEST_PACKAGE" ]]; then
        rm -rf "$TEST_PACKAGE"
    fi
    
    run_test "$CLI_CMD --branch $TEST_BRANCH clone $TEST_PACKAGE" "Clone with branch"
    
    if [[ -d "$TEST_PACKAGE" ]]; then
        rm -rf "$TEST_PACKAGE"
    fi
    
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP --branch $TEST_BRANCH clone $TEST_PACKAGE" "Clone with branch and full options"
    
    if [[ -d "$TEST_PACKAGE" ]]; then
        rm -rf "$TEST_PACKAGE"
    fi
}


test_create() {
    print_test_header "Create Command"

    # Clean up any existing testpackage directory before starting
    if [[ -d "testpackage" ]]; then
        rm -rf testpackage
    fi

    run_test "$CLI_CMD --branch $TEST_BRANCH create testpackage" "Create package with default type"

    if [[ -d "testpackage" ]]; then
        rm -rf testpackage
    fi

    run_test "$CLI_CMD --branch $TEST_BRANCH create testpackage gbp" "Create package with gbp type"

    if [[ -d "testpackage" ]]; then
        rm -rf testpackage
    fi

    run_test "$CLI_CMD --branch $TEST_BRANCH create testpackage gbp tools" "Create package with type and subgroup"

    if [[ -d "testpackage" ]]; then
        rm -rf testpackage
    fi

    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP --branch $TEST_BRANCH create testpackage" "Create with full host options"

    if [[ -d "testpackage" ]]; then
        rm -rf testpackage
    fi

    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP --branch $TEST_BRANCH create testpackage gbp" "Create with full options and type"

    if [[ -d "testpackage" ]]; then
        rm -rf testpackage
    fi

    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP --branch $TEST_BRANCH create testpackage gbp tools" "Create with full options, type and subgroup"

    if [[ -d "testpackage" ]]; then
        rm -rf testpackage
    fi
}


test_disable() {
    print_test_header "Disable Command"
    
    run_test "$CLI_CMD disable" "Disable (auto-detect)"
    run_test "$CLI_CMD disable ." "Disable current directory" 
    run_test "$CLI_CMD disable $TEST_PACKAGE" "Disable package"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP disable" "Disable with full options (auto-detect)"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP disable ." "Disable current directory with full options"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP disable $TEST_PACKAGE" "Disable package with full options"
    
}


test_enable() {
    print_test_header "Enable Command"

    
    run_test "$CLI_CMD enable" "Enable (auto-detect)"
    run_test "$CLI_CMD enable ." "Enable current directory"
    run_test "$CLI_CMD enable $TEST_PACKAGE" "Enable package"
    run_test "$CLI_CMD enable $TEST_PACKAGE gbp" "Enable package with type"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP enable" "Enable with full options (auto-detect)"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP enable ." "Enable current directory with full options"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP enable $TEST_PACKAGE" "Enable package with full options"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP enable $TEST_PACKAGE gbp" "Enable package with type and full options"
    run_test "$CLI_CMD --branch $TEST_BRANCH enable" "Enable with branch (auto-detect)"
    run_test "$CLI_CMD --branch $TEST_BRANCH enable ." "Enable current directory with branch"
    run_test "$CLI_CMD --branch $TEST_BRANCH enable $TEST_PACKAGE" "Enable package with branch"
    run_test "$CLI_CMD --branch $TEST_BRANCH enable $TEST_PACKAGE gbp" "Enable package with type and branch"
    
}


test_getartifacts() {
    print_test_header "Getartifacts Command"

    
    run_test "$CLI_CMD getartifacts" "Get artifacts (auto-detect)"
    run_test "$CLI_CMD getartifacts ." "Get artifacts current directory"
    run_test "$CLI_CMD getartifacts $TEST_PACKAGE" "Get artifacts package"
    run_test "$CLI_CMD getartifacts $TEST_PACKAGE build-amd64" "Get artifacts with job name"
    run_test "$CLI_CMD getartifacts $TEST_PACKAGE build-arm64" "Get artifacts with arm64 job name"
    run_test "$CLI_CMD getartifacts $TEST_PACKAGE publish" "Get artifacts with publish job name"
    run_test "$CLI_CMD getartifacts . build-amd64" "Get artifacts current directory with job name"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP getartifacts" "Get artifacts with full options (auto-detect)"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP getartifacts ." "Get artifacts current directory with full options"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP getartifacts $TEST_PACKAGE" "Get artifacts package with full options"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP getartifacts $TEST_PACKAGE build-amd64" "Get artifacts with job name and full options"
    run_test "$CLI_CMD --branch $TEST_BRANCH getartifacts" "Get artifacts with branch (auto-detect)"
    run_test "$CLI_CMD --branch $TEST_BRANCH getartifacts ." "Get artifacts current directory with branch"
    run_test "$CLI_CMD --branch $TEST_BRANCH getartifacts $TEST_PACKAGE" "Get artifacts package with branch"
    run_test "$CLI_CMD --branch $TEST_BRANCH getartifacts $TEST_PACKAGE build-amd64" "Get artifacts with job name and branch"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP --branch $TEST_BRANCH getartifacts" "Get artifacts with branch and full options (auto-detect)"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP --branch $TEST_BRANCH getartifacts ." "Get artifacts current directory with branch and full options"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP --branch $TEST_BRANCH getartifacts $TEST_PACKAGE" "Get artifacts package with branch and full options"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP --branch $TEST_BRANCH getartifacts $TEST_PACKAGE build-amd64" "Get artifacts with job name, branch and full options"    
    
}


test_list() {
    print_test_header "List Command"

    
    run_test "$CLI_CMD list" "List packages"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP list" "List with full options"
    run_test "$CLI_CMD --branch $TEST_BRANCH list" "List with branch"
    run_test "$CLI_CMD --dump list" "List with dump"
    run_test "$CLI_CMD --dump --host $TEST_HOST --pkg-group $TEST_PKG_GROUP list" "List with dump and full options"
    run_test "$CLI_CMD --dump --branch $TEST_BRANCH --host $TEST_HOST --pkg-group $TEST_PKG_GROUP list" "List with dump, branch and full options"
    
    
}


test_log() {
    print_test_header "Log Command"

    
    run_test "$CLI_CMD log build-amd64" "Log job (auto-detect)"
    run_test "$CLI_CMD log build-amd64 ." "Log job current directory"
    run_test "$CLI_CMD log build-amd64 $TEST_PACKAGE" "Log job for package"
    run_test "$CLI_CMD log build-arm64" "Log arm64 job (auto-detect)"
    run_test "$CLI_CMD log build-arm64 $TEST_PACKAGE" "Log arm64 job for package"
    run_test "$CLI_CMD log publish" "Log publish job (auto-detect)"
    run_test "$CLI_CMD log publish $TEST_PACKAGE" "Log publish job for package"
    run_test "$CLI_CMD log calculate-env" "Log calculate-env job (auto-detect)"
    run_test "$CLI_CMD log calculate-env $TEST_PACKAGE" "Log calculate-env job for package"
    run_test "$CLI_CMD log build-amd64 --wait" "Log job with wait (auto-detect)"
    run_test "$CLI_CMD log build-amd64 . --wait" "Log job current directory with wait"
    run_test "$CLI_CMD log build-amd64 $TEST_PACKAGE --wait" "Log job for package with wait"
    run_test "$CLI_CMD log build-arm64 --wait" "Log arm64 job with wait"
    run_test "$CLI_CMD log build-arm64 $TEST_PACKAGE --wait" "Log arm64 job for package with wait"   
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP log build-amd64" "Log job with full options (auto-detect)"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP log build-amd64 ." "Log job current directory with full options"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP log build-amd64 $TEST_PACKAGE" "Log job for package with full options"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP log build-amd64 --wait" "Log job with full options and wait"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP log build-amd64 $TEST_PACKAGE --wait" "Log job for package with full options and wait"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP --branch $TEST_BRANCH log build-amd64" "Log job with branch and full options"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP --branch $TEST_BRANCH log build-amd64 $TEST_PACKAGE" "Log job for package with branch and full options"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP --branch $TEST_BRANCH log build-amd64 --wait" "Log job with branch, full options and wait"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP --branch $TEST_BRANCH log build-amd64 $TEST_PACKAGE --wait" "Log job for package with branch, full options and wait"
    
    
}


test_mr() {
    print_test_header "Mr (Mergerequest) Command"

    
    run_test "$CLI_CMD mr" "List merge requests (all packages)"
    run_test "$CLI_CMD mr $TEST_PACKAGE" "List merge requests for package"
    run_test "$CLI_CMD --dump mr" "List merge requests with dump"
    run_test "$CLI_CMD --dump mr $TEST_PACKAGE" "List merge requests for package with dump"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP mr" "List merge requests with full options"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP mr $TEST_PACKAGE" "List merge requests for package with full options"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP --dump mr" "List merge requests with full options and dump"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP --dump mr $TEST_PACKAGE" "List merge requests for package with full options and dump"
    run_test "$CLI_CMD --branch $TEST_BRANCH mr" "List merge requests with branch option"
    run_test "$CLI_CMD --branch $TEST_BRANCH mr $TEST_PACKAGE" "List merge requests for package with branch option"
}


test_pdiff() {
    print_test_header "Pdiff Command"

    run_test "$CLI_CMD pdiff" "Print diff (auto-detect)"
    run_test "$CLI_CMD pdiff ." "Print diff current directory"
    run_test "$CLI_CMD pdiff $TEST_PACKAGE" "Print diff package"
    
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP pdiff $TEST_PACKAGE" "Print diff with full options"
}


test_show() {
    print_test_header "Show Command"

    run_test "$CLI_CMD show" "Show package info (auto-detect)"
    run_test "$CLI_CMD show ." "Show current directory info"
    run_test "$CLI_CMD show $TEST_PACKAGE" "Show package info"
    run_test "$CLI_CMD show --branches" "Show with branches (auto-detect)"
    run_test "$CLI_CMD show . --branches" "Show current directory with branches"
    run_test "$CLI_CMD show $TEST_PACKAGE --branches" "Show package with branches"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP show" "Show with host and pkg-group (auto-detect)"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP show $TEST_PACKAGE" "Show package with host and pkg-group"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP show --branches" "Show branches with host and pkg-group (auto-detect)"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP show $TEST_PACKAGE --branches" "Show package branches with host and pkg-group"
    run_test "$CLI_CMD --dump show" "Show with dump (auto-detect)"
    run_test "$CLI_CMD --dump show ." "Show current directory with dump"
    run_test "$CLI_CMD --dump show $TEST_PACKAGE" "Show package with dump"
    run_test "$CLI_CMD --dump show --branches" "Show branches with dump (auto-detect)"
    run_test "$CLI_CMD --dump show $TEST_PACKAGE --branches" "Show package branches with dump"
    run_test "$CLI_CMD --branch $TEST_BRANCH show" "Show with branch (auto-detect)"
    run_test "$CLI_CMD --branch $TEST_BRANCH show $TEST_PACKAGE" "Show package with branch"
    run_test "$CLI_CMD --branch $TEST_BRANCH show $TEST_PACKAGE --branches" "Show package branches with branch option"
    run_test "$CLI_CMD --dump --host $TEST_HOST --pkg-group $TEST_PKG_GROUP show $TEST_PACKAGE" "Show with dump and full options"
    run_test "$CLI_CMD --dump --branch $TEST_BRANCH --host $TEST_HOST --pkg-group $TEST_PKG_GROUP show $TEST_PACKAGE --branches" "Show with dump and all options"
}


test_status() {
    print_test_header "Status Command"

    
    run_test "$CLI_CMD status" "Status (all packages)"
    run_test "$CLI_CMD status ." "Status current directory"
    run_test "$CLI_CMD status $TEST_PACKAGE" "Status package"
    run_test "$CLI_CMD --dump status $TEST_PACKAGE" "Status package with dump"
    run_test "$CLI_CMD --branch $TEST_BRANCH status $TEST_PACKAGE" "Status package with branch"
    run_test "$CLI_CMD --dump --branch $TEST_BRANCH status $TEST_PACKAGE" "Status package with dump and branch"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP status" "Status all packages with full options"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP status ." "Status current directory with full options"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP status $TEST_PACKAGE" "Status package with full options"
    run_test "$CLI_CMD --dump --host $TEST_HOST --pkg-group $TEST_PKG_GROUP status $TEST_PACKAGE" "Status package with dump and full options"
    run_test "$CLI_CMD --branch $TEST_BRANCH --host $TEST_HOST --pkg-group $TEST_PKG_GROUP status $TEST_PACKAGE" "Status package with branch and full options"
    run_test "$CLI_CMD --dump --branch $TEST_BRANCH --host $TEST_HOST --pkg-group $TEST_PKG_GROUP status $TEST_PACKAGE" "Status package with dump, branch and full options"
    
}


test_trigger() {
    print_test_header "Trigger Command"

    run_test "$CLI_CMD trigger $TEST_PACKAGE" "Trigger package build"
    run_test "$CLI_CMD trigger ." "Trigger current directory"
    run_test "$CLI_CMD trigger --all" "Trigger all packages"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger $TEST_PACKAGE" "Trigger package with full options"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger ." "Trigger current directory with full options"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger --all" "Trigger all packages with full options"
    run_test "$CLI_CMD --branch $TEST_BRANCH trigger $TEST_PACKAGE" "Trigger package with branch"
    run_test "$CLI_CMD --branch $TEST_BRANCH trigger ." "Trigger current directory with branch"
    run_test "$CLI_CMD --branch $TEST_BRANCH trigger --all" "Trigger all packages with branch"
    run_test "$CLI_CMD --dump trigger $TEST_PACKAGE" "Trigger package with dump"
    run_test "$CLI_CMD --dump trigger ." "Trigger current directory with dump"
    run_test "$CLI_CMD --dump trigger --all" "Trigger all packages with dump"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger $TEST_PACKAGE" "Trigger package with full options"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger ." "Trigger current directory with full options"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger --all" "Trigger all packages with full options"
    run_test "$CLI_CMD --verbose --branch $TEST_BRANCH trigger $TEST_PACKAGE" "Trigger package with verbose and branch"
    run_test "$CLI_CMD --verbose --dump trigger $TEST_PACKAGE" "Trigger package with verbose and dump"
    run_test "$CLI_CMD --verbose --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger $TEST_PACKAGE" "Trigger package with verbose and full options"
    run_test "$CLI_CMD --verbose --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger ." "Trigger current directory with verbose and full options"
    run_test "$CLI_CMD --verbose --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger --all" "Trigger all packages with verbose and full options"
    run_test "$CLI_CMD --branch $TEST_BRANCH --dump trigger $TEST_PACKAGE" "Trigger package with branch and dump"
    run_test "$CLI_CMD --branch $TEST_BRANCH --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger $TEST_PACKAGE" "Trigger package with branch and full options"
    run_test "$CLI_CMD --branch $TEST_BRANCH --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger ." "Trigger current directory with branch and full options"
    run_test "$CLI_CMD --branch $TEST_BRANCH --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger --all" "Trigger all packages with branch and full options"
    run_test "$CLI_CMD --dump --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger $TEST_PACKAGE" "Trigger package with dump and full options"
    run_test "$CLI_CMD --dump --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger ." "Trigger current directory with dump and full options"
    run_test "$CLI_CMD --dump --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger --all" "Trigger all packages with dump and full options"
    run_test "$CLI_CMD --verbose --branch $TEST_BRANCH --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger $TEST_PACKAGE" "Trigger package with verbose, branch and full options"
    run_test "$CLI_CMD --verbose --dump --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger $TEST_PACKAGE" "Trigger package with verbose, dump and full options"
    run_test "$CLI_CMD --branch $TEST_BRANCH --dump --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger $TEST_PACKAGE" "Trigger package with branch, dump and full options"
    run_test "$CLI_CMD --branch $TEST_BRANCH --dump --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger $TEST_PACKAGE" "Trigger package with branch, dump and full options"
    run_test "$CLI_CMD --verbose --branch $TEST_BRANCH --dump trigger $TEST_PACKAGE" "Trigger package with verbose, branch and dump"
    run_test "$CLI_CMD --verbose --branch $TEST_BRANCH --dump --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger $TEST_PACKAGE" "Trigger package with all options"
    run_test "$CLI_CMD --verbose --branch $TEST_BRANCH --dump --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger ." "Trigger current directory with all options"
    run_test "$CLI_CMD --verbose --branch $TEST_BRANCH --dump --host $TEST_HOST --pkg-group $TEST_PKG_GROUP trigger --all" "Trigger all packages with all options"
}


test_workspace() {
    print_test_header "Workspace Command"

    run_test "$CLI_CMD workspace enter" "Workspace enter (auto-detect)"
    run_test "$CLI_CMD workspace enter $TEST_BRANCH" "Workspace enter with branch"
    run_test "$CLI_CMD --branch $TEST_BRANCH workspace enter" "Workspace enter with global branch"
    run_test "$CLI_CMD --host $TEST_HOST --pkg-group $TEST_PKG_GROUP workspace enter $TEST_BRANCH" "Workspace enter with full options"
}


echo "=========================================="
echo "LichOSCLI Command Test Suite"
echo "=========================================="
echo "Test Package: $TEST_PACKAGE"
echo "Host: $TEST_HOST"
echo "Package Group: $TEST_PKG_GROUP"
echo "Branch: $TEST_BRANCH"
echo "=========================================="
echo -e "${BLUE}Enabled Test Groups:${NC} ${TEST_GROUPS[*]}"
if [[ "$QUIET_MODE" == "true" ]]; then
    echo -e "${BLUE}Output Mode:${NC} Quiet (errors only)"
else
    echo -e "${BLUE}Output Mode:${NC} Show last $SHOW_OUTPUT_LINES lines"
fi
echo "=========================================="
echo ""


for group in "${TEST_GROUPS[@]}"; do
    case $group in
        "basic")
            test_basic
            ;;
        "browse")
            test_browse
            ;;
        "build")
            test_build
            ;;
        "clone")
            test_clone
            ;;
        "create")
            test_create
            ;;
        "disable")
            test_disable
            ;;
        "enable")
            test_enable
            ;;
        "getartifacts")
            test_getartifacts
            ;;
        "list")
            test_list
            ;;
        "log")
            test_log
            ;;
        "mr")
            test_mr
            ;;
        "pdiff")
            test_pdiff
            ;;
        "show")
            test_show
            ;;
        "status")
            test_status
            ;;
        "trigger")
            test_trigger
            ;;
        "workspace")
            test_workspace
            ;;
        *)
            echo -e "${RED}Warning: Unknown test group '$group'${NC}"
            ;;
    esac
done


echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo -e "${GREEN}All tests completed successfully!${NC}"
echo "Total tests run: $test_count"
echo "Tests passed: $passed_count"
echo "Tests failed: 0"
echo ""
echo -e "${GREEN}✓ All $test_count commands executed without errors${NC}"
echo "=========================================="
