package com.deeplinkqr;

import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.util.Log;
import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;
import java.util.Map;

public class DeepLinkActivity extends AppCompatActivity {
    
    private static final String TAG = "DeepLinkQR";
    
    @Override
    protected void onCreate(@Nullable Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        handleDeepLink(getIntent());
    }
    
    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleDeepLink(intent);
    }
    
    private void handleDeepLink(Intent intent) {
        if (intent == null || !Intent.ACTION_VIEW.equals(intent.getAction())) {
            return;
        }
        
        Uri data = intent.getData();
        if (data == null) return;
        
        Log.d(TAG, "Received deep link: " + data.toString());
        
        DeepLinkQRHelper.DeepLinkRoute route = DeepLinkQRHelper.parseDeepLink(data);
        if (route == null) {
            Log.e(TAG, "Failed to parse deep link");
            return;
        }
        
        String path = route.path != null ? route.path : "/";
        
        if (path.startsWith("/profile/")) {
            String userId = route.getSegment(0);
            if (userId != null) openProfile(userId);
        } else if (path.startsWith("/product/")) {
            String productId = route.getSegment(0);
            if (productId != null) openProduct(productId, route.params);
        } else {
            openMainScreen();
        }
    }
    
    private void openProfile(String userId) {
        Log.d(TAG, "Opening profile for user: " + userId);
    }
    
    private void openProduct(String productId, Map<String, String> params) {
        Log.d(TAG, "Opening product: " + productId);
    }
    
    private void openMainScreen() {
        Log.d(TAG, "Opening main screen");
    }
}
