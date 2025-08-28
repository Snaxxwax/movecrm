# MoveCRM Production Deployment Guide

This guide provides step-by-step instructions for deploying MoveCRM to production environments with enterprise-grade security, monitoring, and scalability.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Security Considerations](#security-considerations)
3. [Environment Setup](#environment-setup)
4. [Database Setup](#database-setup)
5. [Application Deployment](#application-deployment)
6. [SSL/TLS Configuration](#ssltls-configuration)
7. [Monitoring Setup](#monitoring-setup)
8. [Backup Configuration](#backup-configuration)
9. [Maintenance Procedures](#maintenance-procedures)
10. [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements

**Minimum Production Requirements:**
- **CPU:** 4 cores (8 recommended)
- **RAM:** 8GB (16GB recommended)
- **Storage:** 100GB SSD (500GB recommended)
- **Network:** 1Gbps connection
- **OS:** Ubuntu 20.04 LTS or newer, CentOS 8+, or RHEL 8+

**Software Dependencies:**
- Docker 20.10+
- Docker Compose 2.0+
- Git 2.25+
- curl, wget, openssl
- Nginx (if not using containerized version)

### External Services

**Required External Services:**
- **Database:** PostgreSQL 13+ (managed service recommended)
- **Cache:** Redis 6+ (managed service recommended)
- **Email:** SMTP service (SendGrid, AWS SES, etc.)
- **Storage:** S3-compatible storage (AWS S3, MinIO, etc.)
- **DNS:** Domain with SSL certificate
- **Monitoring:** Optional but recommended (Sentry, DataDog, etc.)

## Security Considerations

### Network Security

1. **Firewall Configuration:**
   ```bash
   # Allow only necessary ports
   ufw allow 22/tcp    # SSH
   ufw allow 80/tcp    # HTTP
   ufw allow 443/tcp   # HTTPS
   ufw enable
   ```

2. **SSH Hardening:**
   ```bash
   # Disable root login and password authentication
   sudo sed -i 's/#PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
   sudo sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
   sudo systemctl restart sshd
   ```

3. **Docker Security:**
   ```bash
   # Add user to docker group (avoid running as root)
   sudo usermod -aG docker $USER
   newgrp docker
   ```

### Application Security

1. **Environment Variables:** Never commit secrets to version control
2. **JWT Secrets:** Use cryptographically secure random strings (32+ characters)
3. **Database Passwords:** Use strong, unique passwords
4. **API Keys:** Rotate regularly and use least-privilege access
5. **SSL Certificates:** Use valid certificates from trusted CAs

## Environment Setup

### 1. Clone Repository

```bash
git clone https://github.com/your-org/movecrm-improved.git
cd movecrm-improved
```

### 2. Create Production Environment File

```bash
cp backend/.env.production.example .env.production
```

### 3. Configure Environment Variables

Edit `.env.production` with your production values:

```bash
# Application Settings
FLASK_ENV=production
JWT_SECRET_KEY=your-super-secure-jwt-secret-key-change-this-in-production
SECRET_KEY=your-flask-secret-key-change-this-in-production

# Database Configuration (use managed service)
DATABASE_URL=postgresql://username:password@your-db-host:5432/movecrm_production

# Redis Configuration (use managed service)
REDIS_URL=redis://username:password@your-redis-host:6379/0
REDIS_PASSWORD=your-redis-password

# CORS Configuration
ALLOWED_ORIGINS=https://yourdomain.com,https://app.yourdomain.com

# External Services
YOLOE_SERVICE_URL=https://your-yoloe-service-url
SMTP_HOST=your-smtp-host
SMTP_PORT=587
SMTP_USERNAME=your-smtp-username
SMTP_PASSWORD=your-smtp-password
SMTP_FROM_EMAIL=noreply@yourdomain.com

# AWS S3 Configuration
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_S3_BUCKET=your-s3-bucket-name
AWS_S3_REGION=us-east-1

# Monitoring
SENTRY_DSN=your-sentry-dsn-for-error-tracking
GRAFANA_ADMIN_PASSWORD=your-grafana-admin-password
```

### 4. Generate Secure Secrets

```bash
# Generate JWT secret
openssl rand -base64 32

# Generate Flask secret
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate Redis password
openssl rand -base64 24
```

## Database Setup

### Option 1: Managed Database Service (Recommended)

**AWS RDS PostgreSQL:**
1. Create RDS PostgreSQL instance (13.7+)
2. Configure security groups for application access
3. Enable automated backups and point-in-time recovery
4. Set up read replicas for high availability

**Google Cloud SQL:**
1. Create Cloud SQL PostgreSQL instance
2. Configure authorized networks
3. Enable automatic backups and high availability

### Option 2: Self-Managed Database

```bash
# Install PostgreSQL
sudo apt update
sudo apt install postgresql postgresql-contrib

# Create database and user
sudo -u postgres psql
CREATE DATABASE movecrm_production;
CREATE USER movecrm_user WITH ENCRYPTED PASSWORD 'your-secure-password';
GRANT ALL PRIVILEGES ON DATABASE movecrm_production TO movecrm_user;
\q

# Initialize database schema
psql -h localhost -U movecrm_user -d movecrm_production -f docs/database_schema_secure.sql
```

## Application Deployment

### 1. Automated Deployment (Recommended)

```bash
# Make deployment script executable
chmod +x scripts/deploy.sh

# Run deployment
./scripts/deploy.sh deploy
```

### 2. Manual Deployment

```bash
# Build images
docker build -f backend/Dockerfile.production -t movecrm/backend:latest backend/

# Deploy services
docker-compose -f docker-compose.production.yml up -d

# Verify deployment
docker-compose -f docker-compose.production.yml ps
```

### 3. Health Checks

```bash
# Check API health
curl -f http://localhost/health

# Check all services
docker-compose -f docker-compose.production.yml ps
```

## SSL/TLS Configuration

### Option 1: Let's Encrypt (Free)

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d yourdomain.com -d app.yourdomain.com

# Auto-renewal
sudo crontab -e
# Add: 0 12 * * * /usr/bin/certbot renew --quiet
```

### Option 2: Commercial Certificate

1. Purchase SSL certificate from trusted CA
2. Place certificate files in `nginx/ssl/`
3. Update nginx configuration

## Monitoring Setup

### 1. Application Monitoring

**Prometheus Metrics:**
- API response times
- Error rates
- Database connection pool
- Memory and CPU usage

**Grafana Dashboards:**
- System overview
- Application performance
- Business metrics
- Alert management

### 2. Log Aggregation

**Loki + Promtail:**
- Centralized log collection
- Log parsing and indexing
- Integration with Grafana

### 3. Error Tracking

**Sentry Integration:**
```python
# Already configured in app_secure.py
import sentry_sdk
sentry_sdk.init(dsn=os.getenv('SENTRY_DSN'))
```

### 4. Uptime Monitoring

**External Services:**
- Pingdom
- UptimeRobot
- StatusCake

## Backup Configuration

### 1. Database Backups

```bash
# Automated backup script
cat > /etc/cron.daily/movecrm-backup << 'EOF'
#!/bin/bash
BACKUP_DIR="/backups/movecrm"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# Database backup
pg_dump -h your-db-host -U movecrm_user movecrm_production | gzip > $BACKUP_DIR/db_$DATE.sql.gz

# Upload to S3
aws s3 cp $BACKUP_DIR/db_$DATE.sql.gz s3://your-backup-bucket/database/

# Cleanup old backups (keep 30 days)
find $BACKUP_DIR -name "db_*.sql.gz" -mtime +30 -delete
EOF

chmod +x /etc/cron.daily/movecrm-backup
```

### 2. File Backups

```bash
# Backup uploaded files
docker run --rm -v movecrm_backend_uploads:/data -v /backups:/backup \
  alpine tar czf /backup/uploads_$(date +%Y%m%d).tar.gz -C /data .
```

### 3. Configuration Backups

```bash
# Backup configuration
tar czf /backups/config_$(date +%Y%m%d).tar.gz \
  .env.production \
  docker-compose.production.yml \
  nginx/ \
  monitoring/
```

## Maintenance Procedures

### 1. Regular Updates

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Update Docker images
docker-compose -f docker-compose.production.yml pull
docker-compose -f docker-compose.production.yml up -d

# Cleanup old images
docker image prune -f
```

### 2. Database Maintenance

```bash
# Vacuum and analyze database
docker-compose -f docker-compose.production.yml exec backend python -c "
import psycopg2
import os
conn = psycopg2.connect(os.getenv('DATABASE_URL'))
conn.autocommit = True
cursor = conn.cursor()
cursor.execute('VACUUM ANALYZE;')
cursor.close()
conn.close()
"
```

### 3. Log Rotation

```bash
# Configure logrotate
cat > /etc/logrotate.d/movecrm << 'EOF'
/var/log/movecrm/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 movecrm movecrm
    postrotate
        docker-compose -f /path/to/docker-compose.production.yml restart backend
    endscript
}
EOF
```

### 4. Security Updates

```bash
# Check for security updates
sudo unattended-upgrades --dry-run

# Apply security updates
sudo unattended-upgrades
```

## Troubleshooting

### Common Issues

**1. Database Connection Errors**
```bash
# Check database connectivity
docker-compose -f docker-compose.production.yml exec backend \
  python -c "import psycopg2; import os; psycopg2.connect(os.getenv('DATABASE_URL'))"

# Check database logs
docker-compose -f docker-compose.production.yml logs postgres
```

**2. High Memory Usage**
```bash
# Check memory usage
docker stats

# Restart services if needed
docker-compose -f docker-compose.production.yml restart backend
```

**3. SSL Certificate Issues**
```bash
# Check certificate expiration
openssl x509 -in /etc/letsencrypt/live/yourdomain.com/cert.pem -text -noout | grep "Not After"

# Renew certificate
sudo certbot renew
```

**4. Performance Issues**
```bash
# Check application metrics
curl http://localhost:9090/metrics

# Analyze slow queries
docker-compose -f docker-compose.production.yml exec postgres \
  psql -U movecrm_user -d movecrm_production -c "
  SELECT query, mean_time, calls 
  FROM pg_stat_statements 
  ORDER BY mean_time DESC 
  LIMIT 10;"
```

### Log Analysis

```bash
# View application logs
docker-compose -f docker-compose.production.yml logs -f backend

# View nginx logs
docker-compose -f docker-compose.production.yml logs -f nginx

# View system logs
journalctl -u docker -f
```

### Performance Tuning

**Database Optimization:**
```sql
-- Analyze query performance
EXPLAIN ANALYZE SELECT * FROM quotes WHERE tenant_id = 'uuid';

-- Create missing indexes
CREATE INDEX CONCURRENTLY idx_quotes_created_at ON quotes(created_at);
```

**Application Optimization:**
```bash
# Increase worker processes
# Edit docker-compose.production.yml
# Change gunicorn workers from 4 to 8 for high-traffic sites
```

## Scaling Considerations

### Horizontal Scaling

1. **Load Balancer:** Use AWS ALB, Google Cloud Load Balancer, or HAProxy
2. **Multiple Backend Instances:** Scale backend containers across multiple hosts
3. **Database Read Replicas:** Distribute read queries across replicas
4. **CDN:** Use CloudFlare, AWS CloudFront for static assets

### Vertical Scaling

1. **Increase Resources:** Add more CPU/RAM to existing instances
2. **Database Optimization:** Tune PostgreSQL configuration
3. **Redis Optimization:** Configure Redis for optimal performance

## Security Checklist

- [ ] All secrets stored securely (not in code)
- [ ] SSL/TLS certificates configured and auto-renewing
- [ ] Database access restricted to application only
- [ ] Regular security updates applied
- [ ] Backup and disaster recovery tested
- [ ] Monitoring and alerting configured
- [ ] Log aggregation and analysis in place
- [ ] Network security (firewall, VPN) configured
- [ ] User access controls implemented
- [ ] Regular security audits scheduled

## Support and Maintenance

For ongoing support and maintenance:

1. **Documentation:** Keep this guide updated with any changes
2. **Monitoring:** Set up alerts for critical metrics
3. **Backups:** Test restore procedures regularly
4. **Security:** Subscribe to security advisories for all components
5. **Performance:** Monitor and optimize based on usage patterns

## Contact Information

- **Technical Support:** support@movecrm.com
- **Security Issues:** security@movecrm.com
- **Documentation:** docs@movecrm.com

