package com.pricecompare.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import com.pricecompare.di.AppModule
import com.pricecompare.data.remote.Product
import com.pricecompare.util.euro

@Composable
fun CompareDialog(product: Product, onDismiss: () -> Unit) {
    Dialog(onDismissRequest = onDismiss) {
        Surface(tonalElevation = 4.dp, shape = MaterialTheme.shapes.extraLarge) {
            CompareContent(product, onClose = onDismiss)
        }
    }
}

@Composable
fun CompareContent(product: Product, onClose: () -> Unit) {
    val repo = AppModule.repo
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var rows by remember { mutableStateOf<List<RowVM>>(emptyList()) }

    LaunchedEffect(product.id) {
        loading = true
        error = null
        try {
            val offers = repo.compare(product.id).offers

            // Map first ➜ then sort RowVMs
            rows = offers
                .map {
                    RowVM(
                        store = it.store,
                        name = it.raw_name,
                        price = it.price_eur,
                        unitPrice = it.unit_price,
                        collectedAt = it.collected_at ?: ""
                    )
                }
                .sortedWith(
                    compareBy<RowVM> { it.unitPrice ?: Double.POSITIVE_INFINITY }
                        .thenBy { it.price ?: Double.POSITIVE_INFINITY }
                )
        } catch (e: Exception) {
            error = e.message ?: "Gabim i panjohur"
        } finally {
            loading = false
        }
    }

    Column(Modifier.padding(16.dp).widthIn(max = 520.dp)) {
        Text(product.canonical_name, style = MaterialTheme.typography.titleLarge)
        Spacer(Modifier.height(6.dp))
        when {
            loading -> LinearProgressIndicator(Modifier.fillMaxWidth())
            error != null -> Text("Gabim: $error", color = MaterialTheme.colorScheme.error)
            rows.isEmpty() -> Text("S’ka çmime për këtë produkt tani.")
            else -> {
                Spacer(Modifier.height(8.dp))
                LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.heightIn(max = 420.dp)
                ) {
                    items(rows) { r ->
                        ElevatedCard {
                            Row(
                                Modifier.padding(12.dp),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Column(Modifier.weight(1f)) {
                                    Text(r.store, style = MaterialTheme.typography.titleMedium)
                                    if (r.name.isNotBlank()) {
                                        Text(r.name, style = MaterialTheme.typography.bodySmall)
                                    }
                                    Text(
                                        "Përditësuar: ${r.collectedAt}",
                                        style = MaterialTheme.typography.bodySmall
                                    )
                                }
                                Column(
                                    horizontalAlignment = androidx.compose.ui.Alignment.End,
                                    modifier = Modifier.widthIn(min = 120.dp)
                                ) {
                                    Text(euro(r.price), style = MaterialTheme.typography.titleMedium)
                                    Text("(${euro(r.unitPrice)}/njësi)", style = MaterialTheme.typography.bodySmall)
                                }
                            }
                        }
                    }
                }
            }
        }
        Spacer(Modifier.height(12.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            TextButton(onClick = onClose) { Text("Mbyll") }
        }
    }
}

private data class RowVM(
    val store: String,
    val name: String,
    val price: Double?,
    val unitPrice: Double?,
    val collectedAt: String
)
