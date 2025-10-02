package com.pricecompare.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.pricecompare.di.AppModule
import com.pricecompare.data.remote.Product
import com.pricecompare.data.remote.PriceOut
import com.pricecompare.util.euro
import kotlinx.coroutines.launch

@Composable
fun HomeScreen() {
    val repo = AppModule.repo
    val scope = rememberCoroutineScope()

    var essentials by remember { mutableStateOf<List<Product>>(emptyList()) }
    var lowest by remember { mutableStateOf<Map<Int, OfferCard>>(emptyMap()) }
    var loading by remember { mutableStateOf(true) }
    var err by remember { mutableStateOf<String?>(null) }
    var selected by remember { mutableStateOf<Product?>(null) }

    LaunchedEffect(Unit) {
        loading = true; err = null
        try {
            val all = repo.listProducts()
            val wanted = setOf(
                "Milk 1L 2.8%", "Milk 1L 3.5%",
                "Feta / White Cheese 400g", "Yogurt 1kg tub",
                "Butter 250g", "Potatoes per kg"
            )
            val es = all.filter { it.canonical_name in wanted }.sortedBy { it.canonical_name }
            essentials = es

            val map = mutableMapOf<Int, OfferCard>()
            for (p in es) {
                // Try backend compare; if empty, use demo list.
                val offers: List<PriceOut> =
                    runCatching { repo.compare(p.id).offers }.getOrNull().orEmpty()
                        .ifEmpty { demoOffers(p) }

                val min = offers.minByOrNull { it.price_eur }
                if (min != null) {
                    map[p.id] = OfferCard(
                        product = p,
                        store = min.store,
                        price = min.price_eur,
                        unitPrice = min.unit_price
                    )
                }
            }
            lowest = map
        } catch (e: Exception) {
            err = e.message
        } finally { loading = false }
    }

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Text("Krahaso çmimet – Kosovë", style = MaterialTheme.typography.titleLarge)
        Spacer(Modifier.height(8.dp))
        if (loading) LinearProgressIndicator(Modifier.fillMaxWidth())
        err?.let { Text("Gabim: $it", color = MaterialTheme.colorScheme.error) }

        LazyVerticalGrid(
            columns = GridCells.Adaptive(minSize = 180.dp),
            contentPadding = PaddingValues(6.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier.fillMaxSize()
        ) {
            items(essentials, key = { it.id }) { p ->
                val card = lowest[p.id]
                EssentialCard(
                    name = sqName(p.canonical_name),
                    subtitle = card?.store?.let { "Më i lirë te $it" } ?: "—",
                    price = card?.unitPrice ?: card?.price,
                    onCompare = { selected = p }
                )
            }
        }
    }
    selected?.let { CompareBottomSheet(it) { selected = null } }
}

data class OfferCard(val product: Product, val store: String, val price: Double, val unitPrice: Double?)

@Composable
private fun EssentialCard(
    name: String,
    subtitle: String,
    price: Double?,
    onCompare: () -> Unit
) {
    // Same height so the grid lines up perfectly.
    Card(Modifier.fillMaxWidth().height(150.dp)) {
        Column(Modifier.fillMaxSize().padding(12.dp)) {
            Text(name, style = MaterialTheme.typography.titleMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
            Spacer(Modifier.height(4.dp))
            Text(subtitle, style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Spacer(Modifier.weight(1f))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(euro(price), style = MaterialTheme.typography.titleMedium)
                Button(onClick = onCompare) { Text("Krahaso") }
            }
        }
    }
}

/* ---------- Demo data (until real scrapers feed the backend) --------------- */
private fun demoOffers(p: Product): List<PriceOut> {
    fun row(store: String, price: Double, unit: Double? = price) =
        PriceOut(store, p.canonical_name, false, price, unit, null)
    return when (p.canonical_name) {
        "Milk 1L 2.8%" -> listOf(row("Viva Fresh", 0.89), row("SPAR (Wolt)", 0.95), row("Maxi", 0.99))
        "Milk 1L 3.5%" -> listOf(row("SPAR (Wolt)", 0.95), row("Interex", 0.98), row("Viva Fresh", 0.99))
        "Feta / White Cheese 400g" -> listOf(row("Maxi", 2.49, 6.22), row("Viva Fresh", 2.59, 6.47))
        // NOTE: Butter price fixed to be realistic ~2.15€ at Viva (your screenshot).
        "Butter 250g" -> listOf(row("Viva Fresh", 2.15, 8.60), row("Maxi", 2.49, 9.96))
        "Yogurt 1kg tub" -> listOf(row("Interex", 1.29), row("Viva Fresh", 1.39))
        "Potatoes per kg" -> listOf(row("Viva Fresh", 0.59), row("Interex", 0.65))
        else -> emptyList()
    }
}
