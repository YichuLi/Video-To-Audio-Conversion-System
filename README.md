# Video-To-Audio-Conversion-System

## Introduction
This project is a microservices-based distributed system that allows users to authenticate, upload media, convert it, and receive notifications once the conversion is complete.

## Tech Stack

- **Languages**: Python
- **Frameworks**: Flask (for microservices)
- **Messaging**: RabbitMQ (for async job queueing)
- **Database**: MongoDB
- **Containerization**: Docker
- **Orchestration**: Kubernetes

## Services

1. Auth Service (`auth/`)

- Handles **user login, JWT authentication**.

2. Gateway Service (`gateway/`)

- Entry point for clients.
- Handles **authentication**, **routing requests** to backend services.

3. Converter Service (`converter/`)

- Consumes conversion jobs from RabbitMQ.
- Pushes status/results back into storage or notification queue.

4. Notification Service (`notification/`)

- Listens for completed jobs on RabbitMQ.
- Sends **email notifications**.

5. MongoDB (`mongodb/`)

- Stores large media files (via GridFS).

6. RabbitMQ (`rabbit/`)

- Message broker for async communication between **Gateway**, **Converter**, and **Notification**.
- Includes **PVC**, **Ingress**, and **StatefulSet** manifests for persistence.
