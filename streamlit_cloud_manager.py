#!/usr/bin/env python3
"""
Streamlit Cloud Manager
Manages Streamlit Cloud apps via their internal API
"""

import urllib.request
import urllib.parse
import json
import sys
import http.cookiejar
from typing import Dict, Optional, List


class StreamlitCloudManager:
    def __init__(self, session_cookie: str, csrf_token: str):
        """
        Initialize with Streamlit session cookies.
        
        To get these:
        1. Open https://share.streamlit.io in your browser
        2. Open Developer Tools (F12)
        3. Go to Application/Storage → Cookies → https://share.streamlit.io
        4. Copy values of 'streamlit_session' and '_streamlit_csrf' cookies
        """
        self.base_url = "https://share.streamlit.io"
        self.session_cookie = session_cookie
        self.csrf_token = csrf_token
        
        # Set up cookie jar
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )
        
        # Add cookies manually
        self._add_cookies()
    
    def _add_cookies(self):
        """Add authentication cookies to the jar"""
        # Create cookie objects
        session_cookie = http.cookiejar.Cookie(
            version=0, name='streamlit_session', value=self.session_cookie,
            port=None, port_specified=False,
            domain='.streamlit.io', domain_specified=True, domain_initial_dot=True,
            path='/', path_specified=True,
            secure=True, expires=None, discard=True,
            comment=None, comment_url=None, rest={}, rfc2109=False
        )
        
        csrf_cookie = http.cookiejar.Cookie(
            version=0, name='_streamlit_csrf', value=self.csrf_token,
            port=None, port_specified=False,
            domain='.streamlit.io', domain_specified=True, domain_initial_dot=True,
            path='/', path_specified=True,
            secure=True, expires=None, discard=True,
            comment=None, comment_url=None, rest={}, rfc2109=False
        )
        
        self.cookie_jar.set_cookie(session_cookie)
        self.cookie_jar.set_cookie(csrf_cookie)
    
    def _make_request(self, endpoint: str, method: str = 'GET', data: Optional[Dict] = None) -> Dict:
        """Make an authenticated request to Streamlit Cloud API"""
        url = f"{self.base_url}{endpoint}"
        
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-CSRF-Token': self.csrf_token,
        }
        
        if data:
            data = json.dumps(data).encode('utf-8')
        
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        
        try:
            response = self.opener.open(req)
            content = response.read().decode('utf-8')
            
            # Try to parse JSON
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {'raw_content': content, 'content_type': response.headers.get('content-type')}
        
        except urllib.error.HTTPError as e:
            error_content = e.read().decode('utf-8')
            try:
                error_data = json.loads(error_content)
                raise Exception(f"HTTP {e.code}: {error_data}")
            except:
                raise Exception(f"HTTP {e.code}: {error_content}")
    
    def list_apps(self) -> List[Dict]:
        """List all apps"""
        return self._make_request('/api/v1/apps')
    
    def get_app(self, app_id: str) -> Dict:
        """Get details of a specific app"""
        return self._make_request(f'/api/v1/apps/{app_id}')
    
    def get_app_secrets(self, app_id: str) -> Dict:
        """Get secrets for an app"""
        return self._make_request(f'/api/v1/apps/{app_id}/secrets')
    
    def update_app_secrets(self, app_id: str, secrets: Dict) -> Dict:
        """Update secrets for an app"""
        # Secrets are typically in TOML format
        secrets_toml = "\n".join([f'{k} = "{v}"' for k, v in secrets.items()])
        return self._make_request(
            f'/api/v1/apps/{app_id}/secrets',
            method='PUT',
            data={'secrets': secrets_toml}
        )
    
    def reboot_app(self, app_id: str) -> Dict:
        """Reboot an app"""
        return self._make_request(f'/api/v1/apps/{app_id}/reboot', method='POST')
    
    def delete_app(self, app_id: str) -> Dict:
        """Delete an app"""
        return self._make_request(f'/api/v1/apps/{app_id}', method='DELETE')
    
    def find_app_by_name(self, name_substring: str) -> Optional[Dict]:
        """Find app by name (case-insensitive substring match)"""
        apps = self.list_apps()
        
        if isinstance(apps, list):
            for app in apps:
                app_name = app.get('name', '').lower()
                app_url = app.get('url', '').lower()
                if name_substring.lower() in app_name or name_substring.lower() in app_url:
                    return app
        
        return None


def main():
    print("=" * 80)
    print("STREAMLIT CLOUD MANAGER")
    print("=" * 80)
    print("\nTo use this script, you need to provide your Streamlit Cloud session cookies.")
    print("\nSteps:")
    print("1. Open https://share.streamlit.io in your browser (while logged in)")
    print("2. Open Developer Tools (F12 or Cmd+Option+I)")
    print("3. Go to: Application (Chrome) or Storage (Firefox) → Cookies")
    print("4. Find and copy the values of:")
    print("   - streamlit_session")
    print("   - _streamlit_csrf")
    print("\nThen run this script with the cookies as arguments:\n")
    print("python3 streamlit_cloud_manager.py <session_cookie> <csrf_token>\n")
    
    if len(sys.argv) < 3:
        print("\n⚠ No cookies provided. Exiting.\n")
        sys.exit(1)
    
    session_cookie = sys.argv[1]
    csrf_token = sys.argv[2]
    
    print("\n✓ Cookies provided. Connecting to Streamlit Cloud...\n")
    
    manager = StreamlitCloudManager(session_cookie, csrf_token)
    
    try:
        # List all apps
        print("Fetching apps...")
        apps = manager.list_apps()
        
        if isinstance(apps, dict) and 'raw_content' in apps:
            print("❌ Failed to authenticate. Check your cookies.")
            print(f"Response: {apps['raw_content'][:200]}...")
            sys.exit(1)
        
        print(f"\n✓ Found {len(apps)} app(s)\n")
        
        # Find the gujrat-tsr app
        target_app = manager.find_app_by_name('gujrat-tsr')
        
        if not target_app:
            print("❌ Could not find 'gujrat-tsr' app")
            print("\nAvailable apps:")
            for app in apps:
                print(f"  - {app.get('name')} ({app.get('url')})")
            sys.exit(1)
        
        print("=" * 80)
        print("FOUND: gujrat-tsr APP")
        print("=" * 80)
        print(json.dumps(target_app, indent=2))
        
        # Get app ID
        app_id = target_app.get('id')
        
        # Check if we should update secrets
        if len(sys.argv) > 3 and sys.argv[3] == '--update-secrets':
            print("\n" + "=" * 80)
            print("UPDATING SECRETS")
            print("=" * 80)
            
            new_secrets = {
                'API_URL': 'https://agent-gujarat-tsr-642363716512.asia-south1.run.app',
                'API_TIMEOUT': '1200',
                'API_MAX_RETRIES': '2',
            }
            
            print(f"\nNew secrets:")
            for k, v in new_secrets.items():
                print(f"  {k} = {v}")
            
            result = manager.update_app_secrets(app_id, new_secrets)
            print(f"\n✓ Secrets updated: {result}")
        
        # Check if we should reboot
        if len(sys.argv) > 3 and sys.argv[3] == '--reboot':
            print("\n" + "=" * 80)
            print("REBOOTING APP")
            print("=" * 80)
            
            result = manager.reboot_app(app_id)
            print(f"\n✓ App rebooted: {result}")
        
        print("\n" + "=" * 80)
        print("To update secrets, run:")
        print(f"  python3 {sys.argv[0]} <session> <csrf> --update-secrets")
        print("\nTo reboot the app, run:")
        print(f"  python3 {sys.argv[0]} <session> <csrf> --reboot")
        print("=" * 80 + "\n")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
