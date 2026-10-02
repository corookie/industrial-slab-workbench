import subprocess
import sys
import time
import urllib.request
port=int(sys.argv[1])
url=f'http://127.0.0.1:{port}'
for _ in range(60):
    try:
        with urllib.request.urlopen(url+'/api/health',timeout=1) as r:
            if r.status==200:
                subprocess.run(['open',url],check=False)
                break
    except Exception:
        time.sleep(.5)
