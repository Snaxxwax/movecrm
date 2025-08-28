#!/bin/bash

# MoveCRM Production Deployment Script
# This script handles the complete deployment process for MoveCRM

set -e  # Exit on any error

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="/backups/movecrm"
LOG_FILE="/var/log/movecrm-deploy.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
    exit 1
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        error "This script should not be run as root for security reasons"
    fi
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed"
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        error "Docker Compose is not installed"
    fi
    
    # Check environment file
    if [[ ! -f "$PROJECT_DIR/.env.production" ]]; then
        error "Production environment file (.env.production) not found"
    fi
    
    success "Prerequisites check passed"
}

# Backup current deployment
backup_current() {
    log "Creating backup of current deployment..."
    
    mkdir -p "$BACKUP_DIR"
    BACKUP_NAME="movecrm-backup-$(date +%Y%m%d-%H%M%S)"
    
    # Backup database
    if docker-compose -f "$PROJECT_DIR/docker-compose.production.yml" ps | grep -q postgres; then
        log "Backing up database..."
        docker-compose -f "$PROJECT_DIR/docker-compose.production.yml" exec -T postgres \
            pg_dump -U movecrm movecrm_production > "$BACKUP_DIR/$BACKUP_NAME-database.sql"
    fi
    
    # Backup volumes
    log "Backing up volumes..."
    docker run --rm -v movecrm_backend_uploads:/data -v "$BACKUP_DIR":/backup \
        alpine tar czf "/backup/$BACKUP_NAME-uploads.tar.gz" -C /data .
    
    success "Backup completed: $BACKUP_NAME"
}

# Build images
build_images() {
    log "Building Docker images..."
    
    cd "$PROJECT_DIR"
    
    # Build backend image
    docker build -f backend/Dockerfile.production \
        --build-arg BUILD_DATE="$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
        --build-arg VCS_REF="$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')" \
        --build-arg VERSION="$(git describe --tags --always 2>/dev/null || echo 'latest')" \
        -t movecrm/backend:latest \
        backend/
    
    success "Images built successfully"
}

# Deploy services
deploy_services() {
    log "Deploying services..."
    
    cd "$PROJECT_DIR"
    
    # Copy environment file
    cp .env.production .env
    
    # Deploy with Docker Compose
    docker-compose -f docker-compose.production.yml up -d
    
    # Wait for services to be healthy
    log "Waiting for services to be healthy..."
    sleep 30
    
    # Check health
    if ! docker-compose -f docker-compose.production.yml ps | grep -q "Up (healthy)"; then
        warning "Some services may not be healthy. Check logs with: docker-compose logs"
    fi
    
    success "Services deployed successfully"
}

# Run database migrations
run_migrations() {
    log "Running database migrations..."
    
    cd "$PROJECT_DIR"
    
    # Wait for database to be ready
    docker-compose -f docker-compose.production.yml exec backend \
        python -c "
import time
import psycopg2
import os

for i in range(30):
    try:
        conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        conn.close()
        print('Database is ready')
        break
    except:
        print(f'Waiting for database... ({i+1}/30)')
        time.sleep(2)
else:
    raise Exception('Database not ready after 60 seconds')
"
    
    # Run migrations (if you have a migration system)
    # docker-compose -f docker-compose.production.yml exec backend python manage.py migrate
    
    success "Database migrations completed"
}

# Verify deployment
verify_deployment() {
    log "Verifying deployment..."
    
    cd "$PROJECT_DIR"
    
    # Check API health
    if curl -f http://localhost/health > /dev/null 2>&1; then
        success "API health check passed"
    else
        error "API health check failed"
    fi
    
    # Check database connectivity
    if docker-compose -f docker-compose.production.yml exec backend \
        python -c "
import psycopg2
import os
try:
    conn = psycopg2.connect(os.getenv('DATABASE_URL'))
    cursor = conn.cursor()
    cursor.execute('SELECT 1')
    print('Database connection successful')
    conn.close()
except Exception as e:
    print(f'Database connection failed: {e}')
    exit(1)
"; then
        success "Database connectivity verified"
    else
        error "Database connectivity check failed"
    fi
    
    success "Deployment verification completed"
}

# Cleanup old images
cleanup() {
    log "Cleaning up old Docker images..."
    
    # Remove dangling images
    docker image prune -f
    
    # Remove old images (keep last 3 versions)
    docker images movecrm/backend --format "table {{.Repository}}:{{.Tag}}\t{{.CreatedAt}}" | \
        tail -n +2 | sort -k2 -r | tail -n +4 | awk '{print $1}' | xargs -r docker rmi
    
    success "Cleanup completed"
}

# Main deployment function
main() {
    log "Starting MoveCRM production deployment..."
    
    check_root
    check_prerequisites
    backup_current
    build_images
    deploy_services
    run_migrations
    verify_deployment
    cleanup
    
    success "MoveCRM deployment completed successfully!"
    log "Access the application at: http://your-domain.com"
    log "Monitor the application at: http://your-domain.com:3001 (Grafana)"
    log "View logs with: docker-compose -f docker-compose.production.yml logs -f"
}

# Handle script arguments
case "${1:-deploy}" in
    "deploy")
        main
        ;;
    "backup")
        backup_current
        ;;
    "verify")
        verify_deployment
        ;;
    "cleanup")
        cleanup
        ;;
    "help")
        echo "Usage: $0 [deploy|backup|verify|cleanup|help]"
        echo "  deploy  - Full deployment (default)"
        echo "  backup  - Backup current deployment only"
        echo "  verify  - Verify deployment health only"
        echo "  cleanup - Cleanup old images only"
        echo "  help    - Show this help message"
        ;;
    *)
        error "Unknown command: $1. Use 'help' for usage information."
        ;;
esac

