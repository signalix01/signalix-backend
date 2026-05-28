#!/bin/bash

# AlphaEdge Backend - Railway Deployment Script
# This script automates the deployment of all microservices to Railway.app

set -e  # Exit on error

echo "🚀 AlphaEdge Backend - Railway Deployment"
echo "=========================================="
echo ""

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found. Installing..."
    npm install -g @railway/cli
fi

# Check if logged in
echo "🔐 Checking Railway authentication..."
if ! railway whoami &> /dev/null; then
    echo "Please login to Railway:"
    railway login
fi

echo "✅ Authenticated with Railway"
echo ""

# Create or link project
echo "📦 Setting up Railway project..."
if [ ! -f ".railway" ]; then
    echo "Creating new Railway project..."
    railway init
else
    echo "Using existing Railway project"
fi

echo ""
echo "🔧 Setting environment variables..."
echo "Please ensure the following environment variables are set in Railway dashboard:"
echo ""
echo "Required:"
echo "  - DATABASE_URL (Supabase PostgreSQL)"
echo "  - REDIS_URL (Upstash Redis)"
echo "  - JWT_SECRET_KEY"
echo "  - ANTHROPIC_API_KEY"
echo ""
echo "Optional:"
echo "  - OPENAI_API_KEY"
echo "  - GOOGLE_API_KEY"
echo "  - XAI_API_KEY"
echo "  - DEEPSEEK_API_KEY"
echo "  - MISTRAL_API_KEY"
echo "  - SENTRY_DSN"
echo "  - SENDGRID_API_KEY"
echo "  - TWILIO_ACCOUNT_SID"
echo "  - TWILIO_AUTH_TOKEN"
echo ""

read -p "Have you set all required environment variables in Railway? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Please set environment variables in Railway dashboard first:"
    echo "https://railway.app/dashboard"
    exit 1
fi

echo ""
echo "🗄️  Running database migrations..."
railway run alembic upgrade head

echo ""
echo "🌱 Seeding initial data..."
railway run python scripts/init_database.py

echo ""
echo "🚢 Deploying services..."
railway up

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📊 View your deployment:"
echo "   railway open"
echo ""
echo "📝 View logs:"
echo "   railway logs"
echo ""
echo "🔍 Check service status:"
echo "   railway status"
echo ""
echo "🌐 Your services should be available at:"
echo "   https://your-project.railway.app"
echo ""
echo "⚠️  Don't forget to:"
echo "   1. Configure custom domain in Railway dashboard"
echo "   2. Set up SSL certificate"
echo "   3. Configure monitoring alerts"
echo "   4. Test all endpoints"
echo ""
