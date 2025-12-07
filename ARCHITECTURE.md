# Gujarat TSR Agent - Architecture Documentation

## Overview

The Gujarat TSR Agent is designed following **SOLID principles** and a **layered architecture** to ensure maintainability, testability, and scalability.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PRESENTATION LAYER                          │
│  ┌─────────────────────┐    ┌─────────────────────────────────────┐│
│  │   Streamlit App     │    │           FastAPI Server            ││
│  │                     │    │                                     ││
│  │ ┌─────────────────┐ │    │  ┌─────────────────────────────────┐││
│  │ │   Components    │ ├───►│  │        Endpoints                │││
│  │ │ - SingleRecord  │ │    │  │  - /process-record              │││
│  │ │ - BatchProcess  │ │    │  │  - /generate-tsr                │││
│  │ │ - Results       │ │    │  │  - /health                      │││
│  │ └─────────────────┘ │    │  └─────────────────────────────────┘││
│  └─────────────────────┘    └─────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          SERVICE LAYER                              │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │ TranslationServ  │  │   FileService    │  │ ProcessingServ   │  │
│  │                  │  │                  │  │                  │  │
│  │ - translate_to_  │  │ - generate_name  │  │ - process_record │  │
│  │   gujarati       │  │ - create_zip     │  │ - coordinate     │  │
│  │ - translate_to_  │  │ - save_temp      │  │   services       │  │
│  │   english        │  │ - cleanup        │  │                  │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘  │
│  ┌──────────────────┐  ┌──────────────────┐                        │
│  │ ScrapingService  │  │ StreamlitServ    │                        │
│  │                  │  │                  │                        │
│  │ - scrape_record  │  │ - batch_process  │                        │
│  │ - solve_captcha  │  │ - retry_failed   │                        │
│  └──────────────────┘  └──────────────────┘                        │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           CORE LAYER                                │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │     Models       │  │   Interfaces     │  │   Exceptions     │  │
│  │                  │  │                  │  │                  │  │
│  │ - LandRecord     │  │ - ITranslation   │  │ - TSRAgentExc    │  │
│  │   Request        │  │   Service        │  │ - Validation     │  │
│  │ - APIResponse    │  │ - IFileService   │  │   Exception      │  │
│  │ - ProcessResult  │  │ - IScraping      │  │ - Scraping       │  │
│  │ - TSRDocument    │  │   Service        │  │   Exception      │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘  │
│  ┌──────────────────┐                                               │
│  │     Config       │                                               │
│  │                  │                                               │
│  │ - env variables  │                                               │
│  │ - validation     │                                               │
│  └──────────────────┘                                               │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       INFRASTRUCTURE LAYER                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │    AnyRoR        │  │  TSR Generator   │  │    Utilities     │  │
│  │    Package       │  │    Package       │  │                  │  │
│  │                  │  │                  │  │ - JSON Trans     │  │
│  │ - Scraper        │  │ - Extractors     │  │ - Survey Utils   │  │
│  │ - WebDriver      │  │ - Document Gen   │  │ - AI Detector    │  │
│  │ - Captcha        │  │ - Processors     │  │ - Logging        │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

## Layer Descriptions

### 1. Presentation Layer

The presentation layer handles all user interactions and external API requests.

#### Streamlit Application (`app/`)
- **Purpose**: Provides a user-friendly web interface
- **Components**:
  - `streamlit_app_cloud.py`: Main entry point
  - `components/`: Reusable UI components
  - `services/`: Streamlit-specific business logic
  - `api_client.py`: Backend API communication

#### FastAPI Server (`api/server.py`)
- **Purpose**: RESTful API for programmatic access
- **Endpoints**:
  - `POST /process-record`: Process a single land record
  - `POST /generate-tsr`: Generate TSR from uploaded PDF
  - `GET /health`: Health check
  - `GET /debug/environment`: Debug information

### 2. Service Layer

The service layer contains the application's business logic.

#### TranslationService (`services/translation_service.py`)
- **Purpose**: Handle English-Gujarati translations
- **Implements**: `ITranslationService` interface
- **Features**:
  - Cached dictionary lookups
  - AI-powered translations for unknown words
  - Context-aware translation (district, taluka, village)

#### FileService (`services/file_service.py`)
- **Purpose**: Handle all file operations
- **Implements**: `IFileService` interface
- **Features**:
  - Filename generation with sanitization
  - ZIP file creation
  - Temporary file management

#### ScrapingService (`services/scraping_service.py`)
- **Purpose**: Abstract web scraping operations
- **Implements**: `IScrapingService` interface
- **Features**:
  - AnyRoR website interaction
  - CAPTCHA solving coordination

#### ProcessingService (`services/processing_service.py`)
- **Purpose**: Orchestrate the TSR generation workflow
- **Features**:
  - Coordinate between services
  - Handle retry logic
  - Manage parallel processing

#### StreamlitService (`app/services/streamlit_service.py`)
- **Purpose**: Streamlit-specific business logic
- **Features**:
  - Batch processing coordination
  - Progress tracking
  - Result aggregation

### 3. Core Layer

The core layer defines the domain models and contracts.

#### Models (`core/models.py`)
- **LandRecordRequest**: Input data for processing
- **APIResponse**: Standardized API responses
- **ProcessingResult**: Result wrapper with status
- **TSRDocument**: Generated document model

#### Interfaces (`core/interfaces.py`)
- **ITranslationService**: Translation contract
- **IFileService**: File operations contract
- **IScrapingService**: Scraping contract
- **ITSRGenerationService**: TSR generation contract

#### Config (`core/config.py`)
- Centralized configuration management
- Environment variable loading
- Type-safe access with defaults
- Validation

#### Exceptions (`core/exceptions.py`)
- **TSRAgentException**: Base exception
- **ValidationException**: Input validation errors
- **TranslationException**: Translation failures
- **ScrapingException**: Web scraping errors
- **FileOperationException**: File operation errors

### 4. Infrastructure Layer

The infrastructure layer contains external integrations and utilities.

#### AnyRoR Package (`anyror/`)
- **scraper.py**: Main AnyRoR scraping logic
- **captcha_solver.py**: AI-powered CAPTCHA solving
- **webdriver_manager.py**: Selenium WebDriver management

#### TSR Generator Package (`tsr_generator/`)
- **extractors/**: PDF data extraction modules
- **document/**: DOCX generation
- **processors/**: Data processing utilities

#### Utilities (`utils/`)
- **json_translations.py**: Translation dictionaries
- **survey_utils.py**: Survey number handling
- **ai_column_detector.py**: Column mapping for Excel
- **logging_config.py**: Logging configuration

## SOLID Principles Implementation

### Single Responsibility Principle (SRP)
Each class has one responsibility:
- `TranslationService` only handles translations
- `FileService` only handles file operations
- UI components only handle rendering

### Open/Closed Principle (OCP)
- Services are extensible through interfaces
- New translation strategies can be added without modifying existing code
- Configuration is externalized

### Liskov Substitution Principle (LSP)
- All service implementations can be substituted via interfaces
- Mock implementations work for testing

### Interface Segregation Principle (ISP)
- Interfaces are focused and specific
- Clients depend only on methods they use

### Dependency Inversion Principle (DIP)
- High-level modules depend on abstractions (interfaces)
- Dependencies are injected, not instantiated directly
- Factory functions provide configured instances

## Data Flow

### Single Record Processing

```
1. User Input (Streamlit/API)
       │
       ▼
2. Request Validation (core/models.py)
       │
       ▼
3. Translation (TranslationService)
   English → Gujarati
       │
       ▼
4. Web Scraping (anyror package)
   - Form submission
   - CAPTCHA solving
   - PDF download
       │
       ▼
5. TSR Generation (tsr_generator)
   - PDF extraction
   - Data processing
   - DOCX generation
       │
       ▼
6. Response Packaging (FileService)
   - ZIP creation
   - File naming
       │
       ▼
7. Response to User
```

### Batch Processing

```
1. Excel Upload
       │
       ▼
2. Column Mapping (ai_column_detector)
       │
       ▼
3. Parallel Processing (ThreadPoolExecutor)
   ┌───┬───┬───┬───┐
   │   │   │   │   │  (max_workers parallel)
   └───┴───┴───┴───┘
       │
       ▼
4. Results Aggregation
       │
       ▼
5. ZIP Download with all documents
```

## Error Handling Strategy

1. **Validation Errors**: Caught early at API boundary
2. **Translation Errors**: Fallback to original text
3. **Scraping Errors**: Retry with exponential backoff
4. **CAPTCHA Failures**: Retry up to max attempts
5. **File Errors**: Cleanup and re-raise

## Configuration Management

```python
# Configuration is loaded from environment
config = get_config()

# Access type-safe values
headless = config.headless        # bool
timeout = config.captcha_timeout  # int
```

## Testing Strategy

### Unit Tests
- Service layer tests with mocked dependencies
- Model validation tests
- Utility function tests

### Integration Tests
- API endpoint tests with TestClient
- End-to-end processing tests (marked as slow)

### Test Organization
```
tests/
├── conftest.py           # Shared fixtures
├── test_services.py      # Service layer tests
├── test_api.py           # API endpoint tests
└── utils/                # Test utilities
```

## Deployment Architecture

### Local Development
```
Streamlit (localhost:8501) → API Server (localhost:8000)
```

### Cloud Deployment
```
Streamlit Cloud → Cloud Run API
                      │
                      ▼
               Chrome + Selenium
```

## Performance Considerations

1. **Browser Pooling**: Reuse browser instances for multiple requests
2. **Parallel Processing**: Configurable worker count for batch operations
3. **Caching**: Translation results cached in memory
4. **Lazy Loading**: Services initialized on first use
5. **Async Background Tasks**: Cleanup operations run asynchronously

## Security Considerations

1. **API Keys**: Stored in environment variables
2. **Input Validation**: Pydantic models validate all inputs
3. **File Sanitization**: Filenames sanitized before use
4. **No Secrets in Code**: All credentials externalized
