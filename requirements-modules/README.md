# AITBC Requirements Module Management

This directory contains specialized requirement modules for different AITBC service categories.

## Module Structure

### 🤖 AI/ML & Translation (`ai-ml-translation.txt`)
- Translation APIs (OpenAI, Google Translate, DeepL)
- Language processing (NLTK, spaCy, polyglot)
- AI/ML libraries (PyTorch, transformers)
- Quality testing for ML services

### 🔐 Security & Compliance (`security-compliance.txt`)
- Authentication (JWT, password handling)
- Encryption and cryptography
- Compliance monitoring
- Security testing tools

### 🧪 Testing & Quality (`testing-quality.txt`)
- Testing frameworks
- Code quality tools
- Coverage reporting
- Development utilities

## Usage

### Installing Module Dependencies
```bash
# Install AI/ML translation dependencies
pip install -r requirements-modules/ai-ml-translation.txt

# Install security dependencies
pip install -r requirements-modules/security-compliance.txt

# Install testing dependencies
pip install -r requirements-modules/testing-quality.txt
```

### Service Integration
Services can selectively install only the modules they need:

```python
# Example: Multi-language service
# pip install -r requirements-modules/ai-ml-translation.txt

# Example: Payment service with security
# pip install -r requirements-modules/security-compliance.txt

# Example: Development environment
# pip install -r requirements-modules/testing-quality.txt
```

## Benefits

1. **Modular Installation**: Services only install what they need
2. **Reduced Bundle Size**: Smaller Docker images
3. **Clear Dependencies**: Easy to understand what each service needs
4. **Version Management**: Centralized version control for specialized packages
5. **Development Separation**: Dev tools separated from production dependencies

## Migration Strategy

1. **Core Dependencies**: Already in `/opt/aitbc/requirements.txt`
2. **Service-Specific**: Use appropriate module files
3. **Development Only**: Use testing-quality module during development

## Maintenance

- Update module versions when upgrading dependencies
- Add new packages to appropriate modules
- Keep modules focused on their specific domain
- Test module installations regularly
