let amapPromise;

export function loadAmap({ key, securityJsCode }) {
  if (window.AMap) return Promise.resolve(window.AMap);
  if (!key) return Promise.reject(new Error('缺少高德 JS API Key'));

  if (securityJsCode) {
    window._AMapSecurityConfig = {
      securityJsCode,
    };
  }

  if (!amapPromise) {
    amapPromise = new Promise((resolve, reject) => {
      const existingScript = document.getElementById('amap-js-api');
      if (existingScript) {
        existingScript.addEventListener('load', () => resolve(window.AMap), { once: true });
        existingScript.addEventListener('error', () => reject(new Error('高德地图脚本加载失败')), { once: true });
        return;
      }

      const script = document.createElement('script');
      script.id = 'amap-js-api';
      script.async = true;
      script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}`;
      script.onload = () => resolve(window.AMap);
      script.onerror = () => reject(new Error('高德地图脚本加载失败'));
      document.head.appendChild(script);
    });
  }

  return amapPromise;
}
