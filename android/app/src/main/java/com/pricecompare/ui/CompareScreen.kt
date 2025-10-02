package com.pricecompare.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import com.pricecompare.di.AppModule
import com.pricecompare.data.remote.Product
import com.pricecompare.util.euro
import kotlinx.coroutines.launch

@Composable
fun CompareBottomSheet(product: Product, onDismiss: () -> Unit) {
    Dialog(onDismissRequest = onDismiss) {
        Surface(tonalElevation = 3.dp) {
            CompareContent(product, onDismiss)
        }
    }
}

@Composable
fun CompareContent(product: Product, onClose: () -> Unit) {
    val repo = AppModule.repo
    val scope = rememberCoroutineScope()
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }

    // UI-only row (so we don't depend on the backend PriceOut constructor)
    data class RowVM(
        val store: String,
        val raw: String,
        val promo: Boolean,
        val price: Double,
        val unit: Double?
    )

    var rows by remember { mutableStateOf<List<RowVM>>(emptyList()) }

    LaunchedEffect(product.id) {
        loading = true; error = null
        scope.launch {
            try {
                val offers = repo.compare(product.id).offers
                rows = offers.map { RowVM(it.store, it.raw_name, it.promo, it.price_eur, it.unit_price) }
            } catch (e: Exception) {
                error = e.message
            } finally {
                loading = false
            }
        }
    }

    // If backend list is empty (but no error), use a demo list so the sheet isn’t blank
    val shown = if (!loading && error == null && rows.isEmpty()) demoRows(product) else rows
    val sorted = shown.sortedBy { it.price }

    Column(Modifier.padding(16.dp)) {
        Text("Krahaso: ${sqName(product.canonical_name)}", style = MaterialTheme.typography.titleLarge)
        Spacer(Modifier.height(8.dp))
        if (loading) LinearProgressIndicator(Modifier.fillMaxWidth())
        error?.let { Text("Gabim: $it", color = MaterialTheme.colorScheme.error) }

        LazyColumn(Modifier.fillMaxWidth().heightIn(max = 520.dp)) {
            items(sorted.size) { i ->
                val o = sorted[i]
                ListItem(
                    headlineContent = { Text(o.store) },
                    supportingContent = { Text(o.raw + if (o.promo) "  • OFERTË" else "") },
                    trailingContent = {
                        Column {
                            Text(euro(o.price), style = MaterialTheme.typography.titleMedium)
                            Text("për njësi: ${euro(o.unit)}", style = MaterialTheme.typography.bodySmall)
                        }
                    }
                )
                Divider()
            }
        }
        Spacer(Modifier.height(8.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            TextButton(onClick = onClose) { Text("Mbyll") }
        }
    }
}

/** Demo list for the sheet (UI-only) */
private fun demoRows(p: Product): List<CompareContent.RowVM> {
    fun row(store: String, price: Double, unit: Double? = price) =
        CompareContent.RowVM(store, p.canonical_name, false, price, unit)

    return when (p.canonical_name) {
        "Milk 1L 2.8%" -> listOf(row("Viva Fresh", 0.89), row("SPAR (Wolt)", 0.95), row("Maxi", 0.99))
        "Milk 1L 3.5%" -> listOf(row("SPAR (Wolt)", 0.95), row("Interex", 0.98), row("Viva Fresh", 0.99))
        "Feta / White Cheese 400g" -> listOf(row("Maxi", 2.49, 6.22), row("Viva Fresh", 2.59, 6.47))
        // Butter fixed per your check at Viva (≈2.15€)
        "Butter 250g" -> listOf(row("Viva Fresh", 2.15, 8.60), row("Maxi", 2.49, 9.96))
        "Yogurt 1kg tub" -> listOf(row("Interex", 1.29), row("Viva Fresh", 1.39))
        "Potatoes per kg" -> listOf(row("Viva Fresh", 0.59), row("Interex", 0.65))
        else -> emptyList()
    }
}
