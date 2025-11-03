package com.pricecompare.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.pricecompare.data.remote.Product
import com.pricecompare.di.AppModule

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(onCompare: (Product) -> Unit) {
    val repo = AppModule.repo
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var products by remember { mutableStateOf<List<Product>>(emptyList()) }

    LaunchedEffect(Unit) {
        loading = true
        error = null
        try {
            // Change this line if your repo uses a different method.
            products = repo.getAllProducts() // You will need to create this function
        } catch (e: Exception) {
            error = e.message ?: "Gabim i panjohur"
        } finally {
            loading = false
        }
    }

    Scaffold(
        topBar = { TopAppBar(title = { Text("KPC", fontWeight = FontWeight.Bold) }) }
    ) { pad ->
        Box(Modifier.padding(pad)) {
            when {
                loading -> CircularProgressIndicator(Modifier.padding(24.dp))
                error != null -> Text("Gabim: $error", color = MaterialTheme.colorScheme.error)
                else -> ProductList(products = products, onCompare = onCompare)
            }
        }
    }
}

@Composable
private fun ProductList(
    products: List<Product>,
    onCompare: (Product) -> Unit
) {
    LazyColumn(
        contentPadding = PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        items(products) { p ->
            ProductCard(product = p) { onCompare(p) }
        }
    }
}

@Composable
private fun ProductCard(
    product: Product,
    onCompare: () -> Unit
) {
    ElevatedCard {
        Row(
            Modifier
                .fillMaxWidth()
                .padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Column(Modifier.weight(1f)) {
                Text(product.canonical_name, style = MaterialTheme.typography.titleMedium)
            }
            TextButton(onClick = onCompare) { Text("Krahaso") }
        }
    }
}
