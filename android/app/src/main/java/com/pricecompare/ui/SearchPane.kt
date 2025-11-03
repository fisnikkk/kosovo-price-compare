package com.pricecompare.ui // Make sure this package name is correct

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.pricecompare.data.remote.Product
import com.pricecompare.di.AppModule
// import com.pricecompare.util.productMeta // <-- DELETED: This import was failing
import kotlinx.coroutines.delay

@Composable
fun SearchPane() {
    val repo = AppModule.repo
    var q by remember { mutableStateOf("") }
    var results by remember { mutableStateOf<List<Product>>(emptyList()) }
    var loading by remember { mutableStateOf(false) }

    LaunchedEffect(q) {
        loading = true
        try {
            if (q.isBlank()) {
                results = emptyList()
            } else {
                delay(300)
                
                // FIX #1: Your repo doesn't have 'search()'.
                // This is a temporary fix that filters the 'popular' list.
                results = repo.popular().filter {
                    it.canonical_name.contains(q, ignoreCase = true)
                }
            }
        } finally { loading = false }
    }

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        OutlinedTextField(
            value = q, onValueChange = { q = it },
            label = { Text("Kërko") },
            modifier = Modifier.fillMaxWidth()
        )
        if (loading) {
            Spacer(Modifier.height(8.dp))
            LinearProgressIndicator(Modifier.fillMaxWidth())
        }
        LazyColumn {
            items(results, key = { it.id }) { p ->
                Row(Modifier.fillMaxWidth().padding(vertical = 8.dp),
                    horizontalArrangement = Arrangement.SpaceBetween) {
                    Column(Modifier.weight(1f)) {
                        
                        // FIX #2: Replaced 'sqName(p.canonical_name)'
                        Text(p.canonical_name, style = MaterialTheme.typography.bodyLarge)

                        // FIX #3: Commented out 'productMeta' because it is missing
                        // Text(productMeta(p.size_ml_g, p.unit, p.fat_pct), style = MaterialTheme.typography.bodySmall)
                    
                    }
                    TextButton(onClick = { /* open compare if needed */ }) { Text("Krahaso") }
                }
                Divider()
            }
        }
    }
}