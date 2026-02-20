package com.deeplinkqr;

import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.net.Uri;
import java.util.HashMap;
import java.util.Map;

public class DeepLinkQRHelper {
    
    private static final String PLAY_STORE_MARKET = "market://details?id=";
    private static final String PLAY_STORE_WEB = "https://play.google.com/store/apps/details?id=";
    
    public static DeepLinkRoute parseDeepLink(Uri uri) {
        if (uri == null) return null;
        
        String scheme = uri.getScheme();
        String host = uri.getHost();
        String path = uri.getPath();
        
        Map<String, String> params = new HashMap<>();
        if (uri.getQueryParameterNames() != null) {
            for (String key : uri.getQueryParameterNames()) {
                params.put(key, uri.getQueryParameter(key));
            }
        }
        
        return new DeepLinkRoute(scheme, host, path, params);
    }
    
    public static boolean canHandleDeepLink(Context context, Uri uri) {
        Intent intent = new Intent(Intent.ACTION_VIEW, uri);
        PackageManager pm = context.getPackageManager();
        ResolveInfo info = pm.resolveActivity(intent, PackageManager.MATCH_DEFAULT_ONLY);
        return info != null;
    }
    
    public static void openPlayStore(Context context, String packageName) {
        try {
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(PLAY_STORE_MARKET + packageName));
            intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
        } catch (Exception e) {
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(PLAY_STORE_WEB + packageName));
            intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
        }
    }
    
    public static String buildIntentUrl(String scheme, String deepLink, String packageName, String fallbackUrl) {
        String path = deepLink.replaceFirst("^[^:]+://", "");
        return String.format("intent://%s#Intent;scheme=%s;package=%s;S.browser_fallback_url=%s;end",
            path, scheme, packageName, Uri.encode(fallbackUrl));
    }
    
    public static class DeepLinkRoute {
        public final String scheme;
        public final String host;
        public final String path;
        public final Map<String, String> params;
        
        public DeepLinkRoute(String scheme, String host, String path, Map<String, String> params) {
            this.scheme = scheme;
            this.host = host;
            this.path = path;
            this.params = params != null ? params : new HashMap<>();
        }
        
        public String getSegment(int index) {
            if (path == null) return null;
            String[] segments = path.split("/");
            if (index + 1 < segments.length) {
                return segments[index + 1];
            }
            return null;
        }
    }
}
