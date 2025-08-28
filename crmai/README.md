# MoveCRM MVP

A complete multi-tenant CRM system for moving companies with AI-powered item detection, automated pricing, and embeddable quote widgets.

## 🚀 Features

- **Multi-tenant Architecture** - Support multiple moving companies with isolated data
- **AI-Powered Item Detection** - YOLOE-based automatic item recognition from photos
- **Automated Pricing** - Calculate quotes based on cubic footage, labor, and tenant rates
- **Embeddable Widget** - JavaScript widget for customer websites
- **Role-based Access Control** - Admin, staff, and customer roles
- **Real-time Notifications** - Quote status updates and notifications
- **File Upload Support** - Secure image upload with validation
- **Rate Limiting** - Prevent abuse with per-tenant and IP-based limits

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │    Backend      │    │ YOLOE Service   │
│   (React)       │◄──►│   (Flask)       │◄──►│   (FastAPI)     │
│                 │    │                 │    │                 │
│ - Dashboard     │    │ - Multi-tenant  │    │ - Item Detection│
│ - Quote Mgmt    │    │ - SuperTokens   │    │ - RunPod GPU    │
│ - Customer Mgmt │    │ - Rate Limiting │    │ - Batch Process │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌─────────────────┐              │
         │              │   PostgreSQL    │              │
         └──────────────┤   + Redis       │──────────────┘
                        │   + SuperTokens │
                        └─────────────────┘

┌─────────────────┐    ┌─────────────────┐
│ Embeddable      │    │   Widget CDN    │
│ Widget (JS)     │◄──►│   (Nginx)       │
│                 │    │                 │
│ - Quote Form    │    │ - CORS Enabled  │
│ - File Upload   │    │ - Cached Assets │
│ - Responsive    │    │ - Global CDN    │
└─────────────────┘    └─────────────────┘
```

## 📁 Project Structure

```
movecrm-mvp/
├── backend/                 # Flask API server
│   ├── src/
│   │   ├── models/         # Database models
│   │   ├── routes/         # API endpoints
│   │   ├── utils/          # Utilities
│   │   └── main.py         # Application entry point
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── yoloe-service/          # AI detection service
│   ├── src/
│   │   ├── models.py       # Pydantic models
│   │   ├── yoloe_detector.py
│   │   └── runpod_client.py
│   ├── main.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/               # React dashboard
│   ├── src/
│   │   ├── components/     # React components
│   │   ├── hooks/          # Custom hooks
│   │   └── App.jsx
│   ├── package.json
│   ├── Dockerfile
│   └── Dockerfile.dev
├── widget/                 # Embeddable widget
│   ├── src/
│   │   └── movecrm-widget.js
│   ├── examples/
│   │   └── demo.html
│   ├── dist/               # Built widget files
│   ├── build.sh
│   └── README.md
├── docs/                   # Documentation
│   └── database_schema.sql
├── docker-compose.yml      # Local development
└── README.md
```

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose
- Node.js 20+ (for local frontend development)
- Python 3.11+ (for local backend development)

### 1. Clone and Setup

```bash
git clone <repository-url>
cd movecrm-mvp
```

### 2. Environment Configuration

Copy environment files and configure:

```bash
# Backend
cp backend/.env.example backend/.env

# YOLOE Service
cp yoloe-service/.env.example yoloe-service/.env

# Frontend (if needed)
cp frontend/.env.example frontend/.env
```

### 3. Start with Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### 4. Access the Application

- **Frontend Dashboard**: http://localhost:3000
- **Backend API**: http://localhost:5000
- **YOLOE Service**: http://localhost:8001
- **Widget CDN**: http://localhost:8080
- **Database Admin**: http://localhost:8082 (Adminer)
- **File Storage**: http://localhost:9001 (MinIO Console)

## 🔧 Development

### Backend Development

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
flask run --host=0.0.0.0 --port=5000
```

### Frontend Development

```bash
cd frontend
pnpm install
pnpm run dev
```

### YOLOE Service Development

```bash
cd yoloe-service
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

### Widget Development

```bash
cd widget
# Edit src/movecrm-widget.js
# Test with examples/demo.html
./build.sh  # Build for production
```

## 🧪 Testing

### API Testing

Use the provided Postman collection:

```bash
# Import postman/MoveCRM_API.postman_collection.json
# Set environment variables:
# - base_url: http://localhost:5000
# - tenant_slug: demo
```

### Widget Testing

Open `widget/examples/demo.html` in your browser to test the embeddable widget.

## 🚀 Deployment

### Production Deployment

1. **Build Images**:
```bash
docker-compose -f docker-compose.prod.yml build
```

2. **Deploy to Cloud**:
- Use Docker Swarm, Kubernetes, or cloud services
- Configure environment variables for production
- Set up SSL certificates
- Configure CDN for widget distribution

3. **Database Migration**:
```bash
# Run database migrations
docker-compose exec backend flask db upgrade
```

### Environment Variables

#### Backend (.env)
```env
FLASK_ENV=production
DATABASE_URL=postgresql://user:pass@host:5432/movecrm
REDIS_URL=redis://host:6379/0
SUPERTOKENS_CONNECTION_URI=http://supertokens:3567
SECRET_KEY=your-secret-key
YOLOE_SERVICE_URL=http://yoloe-service:8001
```

#### YOLOE Service (.env)
```env
SERVICE_HOST=0.0.0.0
SERVICE_PORT=8001
RUNPOD_API_KEY=your-runpod-key
YOLOE_MODEL_PATH=yolov8n.pt
```

## 📚 API Documentation

### Authentication

The API uses SuperTokens for authentication with multi-tenant support:

```bash
# Login
POST /api/auth/login
{
  "email": "user@company.com",
  "password": "password",
  "tenantSlug": "company-slug"
}
```

### Quote Management

```bash
# Create quote
POST /api/quotes
Headers: X-Tenant-Slug: company-slug

# Get quotes
GET /api/quotes
Headers: X-Tenant-Slug: company-slug

# Public quote submission (widget)
POST /api/public/quote
Headers: X-Tenant-Slug: company-slug
```

### YOLOE Detection

```bash
# Auto detection
POST /api/detect/auto
Content-Type: multipart/form-data

# Text-prompted detection
POST /api/detect/text
{
  "prompt": "furniture items",
  "files": [...]
}
```

## 🔒 Security

- **Multi-tenant Isolation**: All data is isolated by tenant_id
- **Rate Limiting**: Configurable limits per tenant and IP
- **File Upload Validation**: Type and size restrictions
- **CORS Configuration**: Proper cross-origin settings
- **SQL Injection Prevention**: Parameterized queries
- **XSS Protection**: Input sanitization

## 🎨 Widget Customization

The embeddable widget is highly customizable:

```javascript
MoveCRMWidget.init({
  tenantSlug: 'your-company',
  apiUrl: 'https://api.movecrm.com',
  primaryColor: '#2563eb',
  borderRadius: '8px',
  maxFiles: 5,
  maxFileSize: 50 * 1024 * 1024
});
```

## 📊 Monitoring

### Health Checks

All services include health check endpoints:

- Backend: `GET /health`
- YOLOE Service: `GET /health`
- Frontend: `GET /health`

### Logging

Structured logging is configured for all services:

```bash
# View logs
docker-compose logs -f backend
docker-compose logs -f yoloe-service
```

## 🚀 Deployment Recommendations

This project is designed to be deployed in a flexible, cost-effective, and scalable way. The following are recommendations for a production-grade setup that is both powerful and lightweight.

### 1. Frontend (React Dashboard)

The frontend is a static React application. It should not be run in a Node.js server in production. Instead, it should be built and deployed to a static hosting platform.

- **Platform**: **Vercel** (Recommended), Netlify, or Cloudflare Pages.
- **Why**: These platforms offer automatic builds and deployments from your Git repository, a global CDN for high performance, and generous free tiers that are often sufficient for many applications.
- **Setup**:
    1. Create a new project on Vercel and connect it to your Git repository.
    2. Vercel will automatically detect the React frontend and configure the build settings. The `frontend/vercel.json` file provides an optimal configuration.
    3. Set the `VITE_API_URL` environment variable in the Vercel project settings to point to your deployed backend API URL.

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2F<YOUR_GIT_USERNAME>%2F<YOUR_REPO_NAME>&root-directory=frontend&env=VITE_API_URL&envDescription=The%20URL%20of%20your%20deployed%20backend%20API)

*(Note: You will need to replace the repository URL in the deploy button link with your own).*

### 2. Backend (Flask API)

The backend API should be deployed as a containerized application. For cost-effectiveness, use a platform that supports scaling to zero.

- **Platform**: **Google Cloud Run** (Recommended), AWS App Runner, or Render.
- **Why**: These platforms run your Docker containers in a serverless environment. You only pay when your API is receiving requests, which can dramatically lower costs compared to a traditional server that runs 24/7.
- **Setup**:
    1. Build and push the `backend` Docker image to a container registry (e.g., Docker Hub, Google Artifact Registry).
    2. Create a new service on Google Cloud Run, using the image you just pushed.
    3. Configure environment variables for the database, Redis, SuperTokens, etc., pointing to your managed services.

### 3. YOLOE AI Service

The AI service is the most resource-intensive part of the application. Running a GPU server 24/7 is extremely expensive. A serverless GPU platform is the ideal solution.

- **Platform**: **RunPod** (Recommended), Replicate, or Banana.dev.
- **Why**: These services allow you to deploy your model and pay *per-second* for GPU usage. This is the most cost-effective way to provide GPU-powered features.
- **Setup**:
    This repository has been prepared for a streamlined deployment to RunPod.
    1.  **Build the Docker Image**: Use the provided `yoloe-service/Dockerfile.runpod` to build the service container. This Dockerfile is optimized for RunPod's serverless environment.
        ```bash
        docker build -t <your-docker-hub-username>/movecrm-yoloe:latest -f yoloe-service/Dockerfile.runpod ./yoloe-service
        ```
    2.  **Push to a Registry**: Push the built image to a container registry like Docker Hub or Google Artifact Registry.
        ```bash
        docker push <your-docker-hub-username>/movecrm-yoloe:latest
        ```
    3.  **Create a RunPod Endpoint**:
        - Go to RunPod -> Serverless -> My Endpoints and create a new endpoint.
        - Point the endpoint to the Docker image you just pushed.
        - RunPod will provide you with an API endpoint URL.
    4.  **Configure the Backend**:
        - In your backend's environment variables (e.g., in Google Cloud Run), set `YOLOE_SERVICE_URL` to the API endpoint URL provided by RunPod.
        - The backend will then send detection requests to your serverless GPU worker.

### 4. Database, Cache, and Storage

Using managed services for infrastructure is more reliable, scalable, and often cheaper than self-hosting, especially for smaller projects.

- **Database (PostgreSQL)**: **Neon** or **Supabase** (both have free tiers).
- **Cache (Redis)**: **Upstash** (has a serverless free tier).
- **File Storage (S3)**: **Cloudflare R2** (zero egress fees) or **AWS S3**.
- **Authentication**: Use the **SuperTokens Managed Cloud**.

**Configuration**: To configure your application for these managed services, see the production environment templates:
- `backend/.env.production.example`
- `yoloe-service/.env.production.example`

These files serve as a checklist for all the environment variables you will need to set in your production deployment environment (e.g., Google Cloud Run secrets, Vercel environment variables).

### 5. Embeddable Widget

The JavaScript widget is a static file that should be served from a CDN for best performance.

- **Platform**: **Cloudflare R2** (Recommended for zero egress fees) or **AWS S3 + CloudFront**.
- **Why**: Using a global CDN ensures the widget loads quickly for users anywhere in the world, with minimal cost. Serving it from a dedicated container is inefficient.
- **Setup**:
    1.  **Build the Widget**: Run the build script to minify the widget.
        ```bash
        cd widget
        ./build.sh
        ```
    2.  **Upload to CDN**: Upload the minified widget from `widget/dist/movecrm-widget.min.js` to your chosen provider.

        *Example using `wrangler` for Cloudflare R2:*
        ```bash
        # Make sure you have wrangler configured
        wrangler r2 object put your-bucket-name/movecrm-widget.js --file widget/dist/movecrm-widget.min.js --content-type "application/javascript"
        ```

        *Example using AWS CLI for S3 (also works with R2):*
        ```bash
        aws s3 cp widget/dist/movecrm-widget.min.js s3://your-bucket-name/movecrm-widget.js --content-type "application/javascript" --acl public-read
        ```
    3.  **Update Your Website**: In your website's HTML, update the `<script>` tag to point to the new CDN URL of the widget.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

- **Documentation**: Check the `/docs` directory
- **Issues**: Create an issue on GitHub
- **Email**: support@movecrm.com

## 🗺️ Roadmap

- [ ] Advanced AI item recognition
- [ ] Mobile app for field staff
- [ ] Integration with moving truck GPS
- [ ] Customer portal
- [ ] Advanced analytics dashboard
- [ ] Multi-language support
- [ ] API rate limiting dashboard
- [ ] Automated testing suite

