package com.pricecompare

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import com.pricecompare.data.remote.Product
import com.pricecompare.ui.HomeScreen
import com.pricecompare.ui.CompareDialog

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            var selected by remember { mutableStateOf<Product?>(null) }

            MaterialTheme {
                HomeScreen(
                    onCompare = { product -> selected = product }
                )

                selected?.let { product ->
                    CompareDialog(
                        product = product,
                        onDismiss = { selected = null }
                    )
                }
            }
        }
    }
}
