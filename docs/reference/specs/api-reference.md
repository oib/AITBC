# AITBC API Reference (OpenAPI)

This document provides the complete API reference for the AITBC Coordinator API.

## Base URL

```
Production: https://aitbc.bubuit.net/api
Local:      http://127.0.0.1:8001
```

## Authentication

Most endpoints require an API key passed in the header:

```
X-Api-Key: your-api-key
```

## OpenAPI Specification

```yaml
openapi: 3.0.3
info:
  title: AITBC Coordinator API
  version: 1.0.0
  description: API for submitting AI compute jobs and managing the AITBC network

servers:
  - url: https://aitbc.bubuit.net/api
    description: Production
  - url: http://127.0.0.1:8001
    description: Local development

paths:
  /health:
    get:
      summary: Health check
      tags: [System]
      responses:
        '200':
          description: Service is healthy
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    example: ok
                  version:
                    type: string
                    example: 1.0.0

  /v1/jobs:
    post:
      summary: Submit a new job
      tags: [Jobs]
      security:
        - ApiKey: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/JobRequest'
      responses:
        '201':
          description: Job created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Job'
        '400':
          $ref: '#/components/responses/BadRequest'
        '401':
          $ref: '#/components/responses/Unauthorized'

    get:
      summary: List jobs
      tags: [Jobs]
      parameters:
        - name: status
          in: query
          schema:
            type: string
            enum: [pending, running, completed, failed, cancelled]
        - name: limit
          in: query
          schema:
            type: integer
            default: 20
            maximum: 100
        - name: offset
          in: query
          schema:
            type: integer
            default: 0
      responses:
        '200':
          description: List of jobs
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Job'

  /v1/jobs/{job_id}:
    get:
      summary: Get job details
      tags: [Jobs]
      parameters:
        - name: job_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Job details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Job'
        '404':
          $ref: '#/components/responses/NotFound'

  /v1/jobs/{job_id}/cancel:
    post:
      summary: Cancel a job
      tags: [Jobs]
      parameters:
        - name: job_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Job cancelled
        '404':
          $ref: '#/components/responses/NotFound'
        '409':
          description: Job cannot be cancelled (already completed)

  /v1/jobs/available:
    get:
      summary: Get available jobs for miners
      tags: [Miners]
      parameters:
        - name: miner_id
          in: query
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Available job or null
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Job'

  /v1/jobs/{job_id}/claim:
    post:
      summary: Claim a job for processing
      tags: [Miners]
      parameters:
        - name: job_id
          in: path
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                miner_id:
                  type: string
              required:
                - miner_id
      responses:
        '200':
          description: Job claimed
        '409':
          description: Job already claimed

  /v1/jobs/{job_id}/complete:
    post:
      summary: Submit job result
      tags: [Miners]
      parameters:
        - name: job_id
          in: path
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/JobResult'
      responses:
        '200':
          description: Job completed
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Receipt'

  /v1/miners/register:
    post:
      summary: Register a miner
      tags: [Miners]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/MinerRegistration'
      responses:
        '201':
          description: Miner registered
        '400':
          $ref: '#/components/responses/BadRequest'

  /v1/receipts:
    get:
      summary: List receipts
      tags: [Receipts]
      parameters:
        - name: client
          in: query
          schema:
            type: string
        - name: provider
          in: query
          schema:
            type: string
        - name: limit
          in: query
          schema:
            type: integer
            default: 20
      responses:
        '200':
          description: List of receipts
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Receipt'

  /v1/receipts/{receipt_id}:
    get:
      summary: Get receipt details
      tags: [Receipts]
      parameters:
        - name: receipt_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Receipt details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Receipt'
        '404':
          $ref: '#/components/responses/NotFound'

  /explorer/blocks:
    get:
      summary: Get recent blocks
      tags: [Explorer]
      parameters:
        - name: limit
          in: query
          schema:
            type: integer
            default: 10
      responses:
        '200':
          description: List of blocks
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Block'

  /explorer/transactions:
    get:
      summary: Get recent transactions
      tags: [Explorer]
      responses:
        '200':
          description: List of transactions

  /explorer/receipts:
    get:
      summary: Get recent receipts
      tags: [Explorer]
      responses:
        '200':
          description: List of receipts

  /explorer/stats:
    get:
      summary: Get network statistics
      tags: [Explorer]
      responses:
        '200':
          description: Network stats
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/NetworkStats'

components:
  securitySchemes:
    ApiKey:
      type: apiKey
      in: header
      name: X-Api-Key

  schemas:
    JobRequest:
      type: object
      properties:
        prompt:
          type: string
          description: Input prompt
        model:
          type: string
          default: llama3.2
        params:
          type: object
          properties:
            max_tokens:
              type: integer
              default: 256
            temperature:
              type: number
              default: 0.7
            top_p:
              type: number
              default: 0.9
      required:
        - prompt

    Job:
      type: object
      properties:
        job_id:
          type: string
        status:
          type: string
          enum: [pending, running, completed, failed, cancelled]
        prompt:
          type: string
        model:
          type: string
        result:
          type: string
        miner_id:
          type: string
        created_at:
          type: string
          format: date-time
        started_at:
          type: string
          format: date-time
        completed_at:
          type: string
          format: date-time

    JobResult:
      type: object
      properties:
        miner_id:
          type: string
        result:
          type: string
        completed_at:
          type: string
          format: date-time
      required:
        - miner_id
        - result

    Receipt:
      type: object
      properties:
        receipt_id:
          type: string
        job_id:
          type: string
        provider:
          type: string
        client:
          type: string
        units:
          type: number
        unit_type:
          type: string
        price:
          type: number
        model:
          type: string
        started_at:
          type: integer
        completed_at:
          type: integer
        signature:
          $ref: '#/components/schemas/Signature'

    Signature:
      type: object
      properties:
        alg:
          type: string
        key_id:
          type: string
        sig:
          type: string

    MinerRegistration:
      type: object
      properties:
        miner_id:
          type: string
        capabilities:
          type: array
          items:
            type: string
        gpu_info:
          type: object
          properties:
            name:
              type: string
            memory:
              type: string
      required:
        - miner_id
        - capabilities

    Block:
      type: object
      properties:
        height:
          type: integer
        hash:
          type: string
        timestamp:
          type: string
          format: date-time
        transactions:
          type: integer

    NetworkStats:
      type: object
      properties:
        total_jobs:
          type: integer
        active_miners:
          type: integer
        total_receipts:
          type: integer
        block_height:
          type: integer

  responses:
    BadRequest:
      description: Invalid request
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/Error'

    Unauthorized:
      description: Authentication required
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/Error'

    NotFound:
      description: Resource not found
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/Error'

    Error:
      type: object
      properties:
        detail:
          type: string
        error_code:
          type: string
```

## Interactive Documentation

Access the interactive API documentation at:
- **Swagger UI**: https://aitbc.bubuit.net/api/docs
- **ReDoc**: https://aitbc.bubuit.net/api/redoc
