#!/bin/bash
#
# AnimusForge Test Runner
# Comprehensive test execution script with coverage and reporting
#

set -e

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="${PROJECT_ROOT}/src"
TESTS_DIR="${PROJECT_ROOT}/tests"
COVERAGE_DIR="${PROJECT_ROOT}/htmlcov"
REPORTS_DIR="${PROJECT_ROOT}/reports"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================================================
# Helper Functions
# ============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo ""
    echo "============================================================================"
    echo " $1"
    echo "============================================================================"
    echo ""
}

check_dependencies() {
    log_info "Checking dependencies..."
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is not installed"
        exit 1
    fi
    
    # Check pytest
    if ! python3 -c "import pytest" 2>/dev/null; then
        log_error "pytest is not installed. Run: pip install pytest pytest-asyncio pytest-cov"
        exit 1
    fi
    
    # Check if source directory exists
    if [ ! -d "$SOURCE_DIR" ]; then
        log_error "Source directory not found: $SOURCE_DIR"
        exit 1
    fi
    
    # Check if tests directory exists
    if [ ! -d "$TESTS_DIR" ]; then
        log_error "Tests directory not found: $TESTS_DIR"
        exit 1
    fi
    
    log_success "All dependencies satisfied"
}

# ============================================================================
# Test Run Functions
# ============================================================================

run_all_tests() {
    print_header "Running All Tests"
    
    cd "$PROJECT_ROOT"
    
    pytest \
        --cov="$SOURCE_DIR" \
        --cov-report=html:"$COVERAGE_DIR" \
        --cov-report=term-missing \
        --cov-report=xml:"${REPORTS_DIR}/coverage.xml" \
        --cov-fail-under=85 \
        -v \
        --tb=short \
        "$TESTS_DIR"
    
    log_success "All tests completed"
}

run_unit_tests() {
    print_header "Running Unit Tests"
    
    cd "$PROJECT_ROOT"
    
    pytest \
        -m unit \
        --cov="$SOURCE_DIR" \
        --cov-report=html:"${COVERAGE_DIR}/unit" \
        --cov-report=term-missing \
        -v \
        --tb=short \
        "$TESTS_DIR/unit"
    
    log_success "Unit tests completed"
}

run_integration_tests() {
    print_header "Running Integration Tests"
    
    cd "$PROJECT_ROOT"
    
    pytest \
        -m integration \
        --cov="$SOURCE_DIR" \
        --cov-report=html:"${COVERAGE_DIR}/integration" \
        --cov-report=term-missing \
        -v \
        --tb=short \
        "$TESTS_DIR/integration"
    
    log_success "Integration tests completed"
}

run_e2e_tests() {
    print_header "Running End-to-End Tests"
    
    cd "$PROJECT_ROOT"
    
    pytest \
        -m e2e \
        --cov="$SOURCE_DIR" \
        --cov-report=html:"${COVERAGE_DIR}/e2e" \
        --cov-report=term-missing \
        -v \
        --tb=long \
        "$TESTS_DIR/e2e"
    
    log_success "E2E tests completed"
}

run_golden_tasks() {
    print_header "Running Golden Task Tests"
    
    cd "$PROJECT_ROOT"
    
    pytest \
        -m "e2e and golden_task" \
        --cov="$SOURCE_DIR" \
        --cov-report=term-missing \
        -v \
        --tb=long \
        "$TESTS_DIR/e2e"
    
    log_success "Golden task tests completed"
}

run_quick_tests() {
    print_header "Running Quick Tests (Unit + Fast Integration)"
    
    cd "$PROJECT_ROOT"
    
    pytest \
        -m "unit or (integration and not slow)" \
        --cov="$SOURCE_DIR" \
        --cov-report=term-missing \
        -v \
        --tb=short \
        "$TESTS_DIR"
    
    log_success "Quick tests completed"
}

run_specific_test() {
    local test_path="$1"
    
    print_header "Running Specific Test: $test_path"
    
    cd "$PROJECT_ROOT"
    
    pytest \
        --cov="$SOURCE_DIR" \
        --cov-report=term-missing \
        -v \
        --tb=long \
        "$test_path"
    
    log_success "Test completed"
}

run_with_coverage() {
    print_header "Running Tests with Full Coverage Report"
    
    cd "$PROJECT_ROOT"
    mkdir -p "$REPORTS_DIR"
    
    pytest \
        --cov="$SOURCE_DIR" \
        --cov-report=html:"$COVERAGE_DIR" \
        --cov-report=term-missing \
        --cov-report=xml:"${REPORTS_DIR}/coverage.xml" \
        --cov-report=json:"${REPORTS_DIR}/coverage.json" \
        --cov-fail-under=85 \
        -v \
        --tb=short \
        --junit-xml="${REPORTS_DIR}/junit.xml" \
        "$TESTS_DIR"
    
    log_success "Tests completed with coverage report"
    log_info "HTML Coverage: $COVERAGE_DIR/index.html"
    log_info "XML Coverage: $REPORTS_DIR/coverage.xml"
    log_info "JUnit Report: $REPORTS_DIR/junit.xml"
}

run_watch_mode() {
    print_header "Running Tests in Watch Mode"
    
    cd "$PROJECT_ROOT"
    
    if command -v pytest-watch &> /dev/null; then
        pytest-watch \
            --cov="$SOURCE_DIR" \
            --cov-report=term-missing \
            -v \
            --tb=short \
            "$TESTS_DIR"
    else
        log_error "pytest-watch not installed. Run: pip install pytest-watch"
        exit 1
    fi
}

run_parallel_tests() {
    print_header "Running Tests in Parallel"
    
    cd "$PROJECT_ROOT"
    
    if python3 -c "import pytest_xdist" 2>/dev/null; then
        pytest \
            -n auto \
            --cov="$SOURCE_DIR" \
            --cov-report=term-missing \
            -v \
            --tb=short \
            "$TESTS_DIR"
    else
        log_warning "pytest-xdist not installed. Running sequentially..."
        run_all_tests
    fi
}

show_coverage_report() {
    if [ -f "$COVERAGE_DIR/index.html" ]; then
        log_info "Opening coverage report..."
        if command -v open &> /dev/null; then
            open "$COVERAGE_DIR/index.html"
        elif command -v xdg-open &> /dev/null; then
            xdg-open "$COVERAGE_DIR/index.html"
        else
            log_info "Coverage report available at: $COVERAGE_DIR/index.html"
        fi
    else
        log_error "No coverage report found. Run tests first."
    fi
}

# ============================================================================
# Help and Usage
# ============================================================================

show_help() {
    cat << HELP

AnimusForge Test Runner
=======================

Usage: $0 [command] [options]

Commands:
    all             Run all tests with coverage (default)
    unit            Run only unit tests
    integration     Run only integration tests
    e2e             Run only end-to-end tests
    golden          Run golden task tests (GT-003, GT-004, GT-005)
    quick           Run quick tests (unit + fast integration)
    coverage        Run all tests with full coverage report
    parallel        Run tests in parallel (requires pytest-xdist)
    watch           Run tests in watch mode (requires pytest-watch)
    report          Open coverage report in browser
    test <path>     Run specific test file or directory
    help            Show this help message

Options:
    -v, --verbose   Enable verbose output
    -f, --failfast  Stop on first failure
    --no-cov        Disable coverage reporting

Examples:
    $0 all                    # Run all tests
    $0 unit                   # Run only unit tests
    $0 test tests/unit/       # Run specific directory
    $0 test tests/e2e/test_gt003_kill_switch.py  # Run specific file
    $0 coverage               # Full coverage report

Test Pyramid:
    Unit:        70% of tests (Target: 85% line coverage)
    Integration: 25% of tests (Target: 70% line coverage)
    E2E:          5% of tests (Critical paths)

HELP
}

# ============================================================================
# Main Entry Point
# ============================================================================

main() {
    local command="${1:-all}"
    shift || true
    
    case "$command" in
        all)
            check_dependencies
            run_all_tests
            ;;
        unit)
            check_dependencies
            run_unit_tests
            ;;
        integration)
            check_dependencies
            run_integration_tests
            ;;
        e2e)
            check_dependencies
            run_e2e_tests
            ;;
        golden)
            check_dependencies
            run_golden_tasks
            ;;
        quick)
            check_dependencies
            run_quick_tests
            ;;
        coverage)
            check_dependencies
            run_with_coverage
            ;;
        parallel)
            check_dependencies
            run_parallel_tests
            ;;
        watch)
            check_dependencies
            run_watch_mode
            ;;
        report)
            show_coverage_report
            ;;
        test)
            if [ -z "$1" ]; then
                log_error "Please specify a test path"
                show_help
                exit 1
            fi
            check_dependencies
            run_specific_test "$1"
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "Unknown command: $command"
            show_help
            exit 1
            ;;
    esac
}

# Run main
main "$@"
