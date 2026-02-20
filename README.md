# DeepLink QR

QR codes that actually work for Android deep links.

## Problem Solved

Android QR code to deep link flows are broken:
- App-not-installed scenarios cause confusing errors
- Multiple browsers handle intents differently
- Weird default settings break user experience
- Intent handling has countless edge cases

DeepLink QR solves this with smart fallback logic, browser detection, and graceful handling of all scenarios.

## Features

- Smart QR Code Generation - Creates QR codes with intelligent redirect logic
- App-Not-Installed Handling - Gracefully falls back to Play Store or web
- Browser Detection - Automatically detects Android, iOS, or desktop
- Analytics Dashboard - Track scan-to-open rates by platform
- Android SDK - Helper classes for easy integration

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the Server

```bash
python main.py
```

Or with uvicorn:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Open Dashboard

Navigate to `http://localhost:8000` to access the QR code generator dashboard.

## API Usage

### Create a Deep Link

```bash
curl -X POST "http://localhost:8000/api/links" \
  -H "Content-Type: application/json" \
  -d '{
    "app_scheme": "myapp",
    "app_package": "com.example.myapp",
    "fallback_url": "https://play.google.com/store/apps/details?id=com.example.myapp",
    "custom_path": "profile/12345"
  }'
```

Response:
```json
{
  "id": "abc123",
  "short_url": "http://localhost:8000/r/abc123",
  "qr_code": "data:image/png;base64,...",
  "analytics_url": "http://localhost:8000/analytics/abc123"
}
```

### Get Analytics

```bash
curl "http://localhost:8000/api/analytics/abc123"
```

## Android Integration

### 1. Add Intent Filter

In your `AndroidManifest.xml`:

```xml
<activity android:name=".MainActivity">
    <intent-filter>
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.DEFAULT" />
        <category android:name="android.intent.category.BROWSABLE" />
        <data android:scheme="myapp" />
    </intent-filter>
</activity>
```

### 2. Handle Deep Links

```java
@Override
protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    
    Intent intent = getIntent();
    Uri data = intent.getData();
    
    if (data != null) {
        String path = data.getPath();
        handleDeepLink(path);
    }
}
```

### 3. Use the SDK Helper

Copy `sdk/android/DeepLinkQRHelper.java` to your project.

## How It Works

### Smart Redirect Flow

1. User scans QR code -> Goes to `/r/{link_id}`
2. Server detects device type from User-Agent header
3. Android devices receive HTML with intent-based redirect
4. iOS devices get universal link handling
5. Desktop redirects to fallback URL (Play Store/web)

### Intent Strategy (Android)

```
intent://profile/123#Intent;
    scheme=myapp;
    package=com.example.myapp;
    S.browser_fallback_url=https://play.google.com/store/apps/details?id=com.example.myapp;
end
```

This approach:
- Opens the app if installed
- Falls back to Play Store if not installed
- Works across Chrome, Samsung Internet, and other browsers

## Project Structure

```
├── main.py                 # FastAPI application
├── database.py             # SQLAlchemy models
├── requirements.txt        # Python dependencies
├── templates/              # HTML templates
│   ├── dashboard.html      # QR code generator UI
│   ├── smart_redirect.html # Redirect handler
│   ├── analytics.html      # Analytics dashboard
│   └── sdk_android.html    # SDK documentation
└── sdk/
    └── android/
        ├── DeepLinkQRHelper.java  # SDK helper class
        └── DeepLinkActivity.java  # Example activity
```

## Deployment

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Railway / Render

1. Push to GitHub
2. Connect to Railway or Render
3. Set build: `pip install -r requirements.txt`
4. Set start: `uvicorn main:app --host 0.0.0.0 --port $PORT`

## Testing

### Test Deep Links with ADB

```bash
adb shell am start -W -a android.intent.action.VIEW \
    -d "myapp://profile/123" com.example.myapp
```

## Browser Compatibility

- Chrome (Android)
- Samsung Internet
- Firefox (Android)
- Chrome (iOS)
- Safari (iOS)

## License

MIT

Built for mobile developers who are tired of broken QR code flows.
