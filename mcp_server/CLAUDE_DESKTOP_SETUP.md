# Claude Desktop Setup Guide

Complete guide for configuring the TSR Tools MCP Server with Claude Desktop.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Setup](#quick-setup)
3. [Detailed Configuration](#detailed-configuration)
4. [Usage Examples](#usage-examples)
5. [Troubleshooting](#troubleshooting)
6. [Advanced Configuration](#advanced-configuration)

---

## Prerequisites

### 1. Install Claude Desktop

Download and install Claude Desktop:
- **Mac**: Download from Anthropic website
- **Windows**: Download from Anthropic website
- **Linux**: Use AppImage or build from source

### 2. Deploy MCP Server

Follow [DEPLOYMENT.md](DEPLOYMENT.md) to:
- Install dependencies
- Set up environment variables
- Test the MCP server

### 3. Get API Keys

Ensure you have:
- Google Gemini API key (from https://makersuite.google.com/app/apikey)

---

## Quick Setup

### Step 1: Locate Configuration File

Find your Claude Desktop configuration file:

**macOS:**
```bash
~/Library/Application Support/Claude/claude_desktop_config.json
```

**Windows:**
```bash
%APPDATA%\Claude\claude_desktop_config.json
```

**Linux:**
```bash
~/.config/Claude/claude_desktop_config.json
```

### Step 2: Add MCP Server Configuration

Open the configuration file and add:

```json
{
  "mcpServers": {
    "tsr-tools": {
      "command": "python",
      "args": [
        "/absolute/path/to/agent-gujrat-tsr/mcp_server/server.py"
      ],
      "env": {
        "PYTHONPATH": "/absolute/path/to/agent-gujrat-tsr",
        "GOOGLE_API_KEY": "your_actual_api_key_here"
      }
    }
  }
}
```

**⚠️ Important**:
- Replace `/absolute/path/to/agent-gujrat-tsr` with actual path
- Replace `your_actual_api_key_here` with your Google API key
- Use forward slashes `/` even on Windows

### Step 3: Restart Claude Desktop

1. Close Claude Desktop completely
2. Reopen Claude Desktop
3. MCP server should load automatically

### Step 4: Verify Installation

In Claude Desktop, type:

```
What tools do you have available?
```

You should see:
- `fetch_pdf_from_anyror`
- `analyze_land_record`
- `generate_tsr_document`
- `batch_process_records`

---

## Detailed Configuration

### Configuration File Structure

```json
{
  "mcpServers": {
    "tsr-tools": {
      "command": "python",
      "args": ["/path/to/mcp_server/server.py"],
      "env": {
        "PYTHONPATH": "/path/to/project",
        "GOOGLE_API_KEY": "your_key",
        "OUTPUT_DIR": "output",
        "LOG_LEVEL": "INFO"
      },
      "autoStart": true,
      "restartOnError": true
    }
  }
}
```

### Configuration Options

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `command` | string | Yes | Python executable path |
| `args` | array | Yes | Arguments (server.py path) |
| `env` | object | Yes | Environment variables |
| `autoStart` | boolean | No | Start on Claude launch (default: true) |
| `restartOnError` | boolean | No | Auto-restart on crash (default: true) |

### Platform-Specific Paths

#### macOS Example

```json
{
  "mcpServers": {
    "tsr-tools": {
      "command": "/usr/local/bin/python3",
      "args": [
        "/Users/yourusername/projects/agent-gujrat-tsr/mcp_server/server.py"
      ],
      "env": {
        "PYTHONPATH": "/Users/yourusername/projects/agent-gujrat-tsr",
        "GOOGLE_API_KEY": "AIzaSy..."
      }
    }
  }
}
```

#### Windows Example

```json
{
  "mcpServers": {
    "tsr-tools": {
      "command": "C:/Python311/python.exe",
      "args": [
        "C:/Users/YourName/agent-gujrat-tsr/mcp_server/server.py"
      ],
      "env": {
        "PYTHONPATH": "C:/Users/YourName/agent-gujrat-tsr",
        "GOOGLE_API_KEY": "AIzaSy..."
      }
    }
  }
}
```

#### Linux Example

```json
{
  "mcpServers": {
    "tsr-tools": {
      "command": "/usr/bin/python3",
      "args": [
        "/home/username/agent-gujrat-tsr/mcp_server/server.py"
      ],
      "env": {
        "PYTHONPATH": "/home/username/agent-gujrat-tsr",
        "GOOGLE_API_KEY": "AIzaSy..."
      }
    }
  }
}
```

### Using Virtual Environment

If using a virtual environment:

**macOS/Linux:**
```json
{
  "mcpServers": {
    "tsr-tools": {
      "command": "/path/to/agent-gujrat-tsr/venv/bin/python",
      "args": ["/path/to/agent-gujrat-tsr/mcp_server/server.py"],
      "env": {
        "PYTHONPATH": "/path/to/agent-gujrat-tsr",
        "GOOGLE_API_KEY": "your_key"
      }
    }
  }
}
```

**Windows:**
```json
{
  "mcpServers": {
    "tsr-tools": {
      "command": "C:/path/to/agent-gujrat-tsr/venv/Scripts/python.exe",
      "args": ["C:/path/to/agent-gujrat-tsr/mcp_server/server.py"],
      "env": {
        "PYTHONPATH": "C:/path/to/agent-gujrat-tsr",
        "GOOGLE_API_KEY": "your_key"
      }
    }
  }
}
```

---

## Usage Examples

Once configured, you can use natural language to interact with the tools:

### Example 1: Fetch a PDF

```
Fetch the land record PDF for:
- District: Kutch
- Taluka: Bhuj
- Village: Trambo
- Survey Number: 51
```

Claude will:
1. Use `fetch_pdf_from_anyror` tool
2. Translate names to Gujarati
3. Download the PDF
4. Return the file path and metadata

### Example 2: Analyze a PDF

```
Analyze the PDF at output/pdfs/Survey No.51.pdf
```

Claude will:
1. Use `analyze_land_record` tool
2. Extract land details
3. Extract mutation entries
4. Return structured JSON data
5. Summarize findings in readable format

### Example 3: Generate TSR

```
Generate a Title Search Report for the PDF at output/pdfs/Survey No.51.pdf
```

Claude will:
1. Use `generate_tsr_document` tool
2. Extract all required information
3. Generate professional DOCX document
4. Return the TSR file path

### Example 4: Batch Processing

```
Process all land records from the Excel file at data/records.xlsx
using 5 parallel workers
```

Claude will:
1. Use `batch_process_records` tool
2. Auto-detect Excel columns
3. Process records in parallel
4. Generate results Excel file
5. Provide summary statistics

### Example 5: Complex Workflow

```
Please:
1. Fetch PDFs for survey numbers 51, 52, 53 in Trambo village, Bhuj taluka, Kutch district
2. Analyze each PDF
3. Generate TSR documents for all of them
4. Summarize the ownership details
```

Claude will:
1. Use tools sequentially
2. Track progress
3. Handle errors gracefully
4. Provide comprehensive summary

---

## Troubleshooting

### Issue 1: Server Not Loading

**Symptom**: Tools not available in Claude Desktop

**Solutions**:

1. **Check Configuration File**
   ```bash
   # macOS/Linux
   cat ~/Library/Application\ Support/Claude/claude_desktop_config.json

   # Verify JSON is valid
   python -m json.tool claude_desktop_config.json
   ```

2. **Check Logs**

   **macOS:**
   ```bash
   tail -f ~/Library/Logs/Claude/mcp-*.log
   ```

   **Windows:**
   ```powershell
   Get-Content "$env:APPDATA\Claude\logs\mcp-*.log" -Tail 50
   ```

   **Linux:**
   ```bash
   tail -f ~/.config/Claude/logs/mcp-*.log
   ```

3. **Verify Python Path**
   ```bash
   # Test the exact command from config
   /path/to/python /path/to/server.py

   # Should output: "Starting TSR Tools MCP Server..."
   ```

### Issue 2: Import Errors

**Symptom**: `ModuleNotFoundError` in logs

**Solutions**:

1. **Verify PYTHONPATH**
   ```json
   {
     "env": {
       "PYTHONPATH": "/correct/absolute/path/to/agent-gujrat-tsr"
     }
   }
   ```

2. **Test Imports**
   ```bash
   cd /path/to/agent-gujrat-tsr
   python -c "from services.processing_service import LandRecordProcessor"
   ```

3. **Check Dependencies**
   ```bash
   pip list | grep -E "pandas|selenium|mcp"
   ```

### Issue 3: API Key Issues

**Symptom**: Authentication errors in tool responses

**Solutions**:

1. **Verify API Key in Config**
   ```json
   {
     "env": {
       "GOOGLE_API_KEY": "AIzaSy..."  # Must start with AIzaSy
     }
   }
   ```

2. **Test API Key**
   ```bash
   export GOOGLE_API_KEY="your_key"
   python -c "
   from langchain_google_genai import ChatGoogleGenerativeAI
   llm = ChatGoogleGenerativeAI(model='gemini-pro')
   print(llm.invoke('test'))
   "
   ```

### Issue 4: Chrome/ChromeDriver Issues

**Symptom**: PDF fetching fails with WebDriver errors

**Solutions**:

1. **Install Chrome**
   ```bash
   # Ubuntu/Debian
   sudo apt install chromium-browser

   # macOS
   brew install --cask google-chrome

   # Check version
   google-chrome --version
   ```

2. **Clear Driver Cache**
   ```bash
   rm -rf ~/.wdm/
   ```

### Issue 5: Permission Issues

**Symptom**: `Permission denied` when writing files

**Solutions**:

1. **Check Output Directory**
   ```bash
   ls -la output/
   chmod -R 755 output/
   ```

2. **Create Output Directory**
   ```bash
   mkdir -p output/pdfs output/tsr
   ```

### Issue 6: Server Crashes

**Symptom**: Tools work initially but then stop

**Solutions**:

1. **Enable Auto-Restart**
   ```json
   {
     "mcpServers": {
       "tsr-tools": {
         "restartOnError": true
       }
     }
   }
   ```

2. **Check Memory**
   ```bash
   # Monitor memory usage
   htop
   # or
   top
   ```

3. **Reduce Parallel Workers**
   ```json
   {
     "env": {
       "MAX_WORKERS": "2"  # Reduce from default 3
     }
   }
   ```

---

## Advanced Configuration

### Multiple Environments

Configure different servers for dev/prod:

```json
{
  "mcpServers": {
    "tsr-tools-dev": {
      "command": "python",
      "args": ["/path/to/dev/mcp_server/server.py"],
      "env": {
        "PYTHONPATH": "/path/to/dev",
        "GOOGLE_API_KEY": "dev_key",
        "OUTPUT_DIR": "output_dev"
      }
    },
    "tsr-tools-prod": {
      "command": "python",
      "args": ["/path/to/prod/mcp_server/server.py"],
      "env": {
        "PYTHONPATH": "/path/to/prod",
        "GOOGLE_API_KEY": "prod_key",
        "OUTPUT_DIR": "output_prod"
      }
    }
  }
}
```

### Custom Output Directories

```json
{
  "env": {
    "OUTPUT_DIR": "/custom/output/path",
    "PDF_DIR": "/custom/pdfs",
    "TSR_DIR": "/custom/tsrs"
  }
}
```

### Logging Configuration

```json
{
  "env": {
    "LOG_LEVEL": "DEBUG",
    "LOG_FILE": "/var/log/tsr-mcp-server.log"
  }
}
```

### Performance Tuning

```json
{
  "env": {
    "MAX_WORKERS": "5",
    "HEADLESS": "true",
    "CHROME_OPTIONS": "--no-sandbox --disable-dev-shm-usage"
  }
}
```

---

## Verification Checklist

After configuration, verify:

- [ ] Configuration file is valid JSON
- [ ] Paths are absolute (not relative)
- [ ] Python path is correct
- [ ] PYTHONPATH points to project root
- [ ] API key is set correctly
- [ ] Output directory exists and is writable
- [ ] Chrome/Chromium is installed
- [ ] Claude Desktop restarted
- [ ] Tools appear in Claude
- [ ] Test tool execution works

---

## Testing Your Setup

### Test 1: Check Tools Available

In Claude Desktop:
```
List all available MCP tools
```

Expected: Should show 4 TSR tools

### Test 2: Simple Tool Test

```
Use the analyze_land_record tool to validate a non-existent PDF at /test.pdf
```

Expected: Should return JSON error (file not found)

### Test 3: Translation Test

```
Use fetch_pdf_from_anyror to fetch:
- District: Kutch (in English)
- Taluka: Bhuj
- Village: Trambo
- Survey: 51
```

Expected: Should translate to Gujarati and attempt fetch

### Test 4: Full Workflow

```
If you have a land record PDF, please:
1. Analyze it
2. Generate a TSR document
3. Summarize the findings
```

Expected: Complete workflow execution

---

## Best Practices

### 1. Security

- ✅ Use environment variables for API keys
- ✅ Don't commit config files with keys to Git
- ✅ Restrict config file permissions:
  ```bash
  chmod 600 ~/Library/Application\ Support/Claude/claude_desktop_config.json
  ```

### 2. Performance

- ✅ Use headless mode (default)
- ✅ Adjust workers based on system resources
- ✅ Monitor disk space in output directory

### 3. Maintenance

- ✅ Regularly update dependencies
- ✅ Monitor logs for errors
- ✅ Backup configuration file
- ✅ Keep API keys secure

### 4. Development

- ✅ Use separate dev/prod configurations
- ✅ Test with sample data first
- ✅ Validate tools before production use

---

## Example Prompts for Claude

Here are effective prompts to use with the TSR tools:

### Fetching PDFs

```
Fetch land record PDFs for the following locations:
1. Kutch/Bhuj/Trambo/51
2. Kutch/Bhuj/Trambo/52
3. Kutch/Bhuj/Trambo/53

Please process them one by one and report progress.
```

### Analyzing PDFs

```
Analyze the land record PDF at output/pdfs/Survey No.51.pdf
and provide:
1. Current owner details
2. Total land area
3. List of all transactions
4. Any mortgages or encumbrances
```

### Generating TSRs

```
Generate Title Search Reports for all PDFs in output/pdfs/
and include these custom findings:
- "No encumbrances found"
- "Clear marketable title"
```

### Batch Processing

```
Process the Excel file at data/land_records.xlsx with these requirements:
1. Use 3 parallel workers
2. Auto-detect column names
3. Generate TSR for each record
4. Create summary report
5. List any failed records with reasons
```

---

## Support Resources

- **Documentation**: See `mcp_server/README.md`
- **Deployment**: See `DEPLOYMENT.md`
- **GitHub Issues**: Report bugs and request features
- **Logs**: Check MCP logs for detailed errors

---

## Update Instructions

When updating the MCP server:

```bash
# 1. Pull latest changes
cd /path/to/agent-gujrat-tsr
git pull

# 2. Update dependencies
pip install --upgrade -r requirements.txt
pip install --upgrade -r mcp_server/requirements.txt

# 3. Restart Claude Desktop
# No config changes needed unless specified in release notes
```

---

## Quick Reference

### Config File Locations

| Platform | Path |
|----------|------|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

### Log File Locations

| Platform | Path |
|----------|------|
| macOS | `~/Library/Logs/Claude/mcp-*.log` |
| Windows | `%APPDATA%\Claude\logs\mcp-*.log` |
| Linux | `~/.config/Claude/logs/mcp-*.log` |

### Essential Commands

```bash
# Validate JSON config
python -m json.tool claude_desktop_config.json

# Test MCP server
python mcp_server/server.py

# Check Python path
which python

# View live logs (macOS/Linux)
tail -f ~/Library/Logs/Claude/mcp-*.log
```

---

**Setup Status**: Production-ready ✅

**Last Updated**: December 3, 2025

**Questions?** Check the troubleshooting section or review logs for detailed error messages.
