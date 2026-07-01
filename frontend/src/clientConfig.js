let clientConfigPromise;

export function getClientConfig() {
  if (!clientConfigPromise) {
    clientConfigPromise = fetch('/api/client-config')
      .then((response) => {
        if (!response.ok) {
          throw new Error(`客户端配置加载失败：${response.status}`);
        }
        return response.json();
      })
      .catch(() => ({ amap: { enabled: false, js_api_key: '', security_js_code: '' } }));
  }

  return clientConfigPromise;
}
