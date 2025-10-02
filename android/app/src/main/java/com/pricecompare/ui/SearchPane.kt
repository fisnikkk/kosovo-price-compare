package com.pricecompare.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.pricecompare.di.AppModule
import com.pricecompare.data.remote.Product
import kotlinx.coroutines.launch

@Composable
fun SearchPane(onProductSelected: (Product) -> Unit) {
    val repo = AppModule.repo
    val scope = rememberCoroutineScope()
    var q by remember { mutableStateOf("") }
    var results by remember { mutableStateOf(listOf<Product>()) }
    var loading by remember { mutableStateOf(false) }
    var err by remember { mutableStateOf<String?>(null) }

    Column {
        OutlinedTextField(
            value = q, onValueChange = { q = it },
            modifier = Modifier.fillMaxWidth(),
            label = { Text("Search (e.g., Milk 1L 2.8%)") }
        )
        Spacer(Modifier.height(8.dp))
        Button(onClick = {
            loading = true; err = null
            scope.launch {
                try { results = if (q.isBlank()) repo.listProducts() else repo.search(q) }
                catch (e: Exception) { err = e.message }
                loading = false
            }
        }) { Text("Search") }

        if (loading) LinearProgressIndicator(Modifier.fillMaxWidth())
        err?.let { Text("Error: $it", color = MaterialTheme.colorScheme.error) }

        LazyColumn(Modifier.fillMaxWidth().padding(top = 8.dp)) {
            items(results.size) { i ->
                val p = results[i]
                ListItem(
                    headlineContent = { Text(p.canonical_name) },
                    supportingContent = { Text("${p.category} • unit ${p.unit}") },
                    modifier = Modifier.clickable { onProductSelected(p) }
                )
                Divider()
            }
        }
    }
}
