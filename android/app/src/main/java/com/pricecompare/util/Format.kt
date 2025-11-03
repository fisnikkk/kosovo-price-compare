package com.pricecompare.util

import java.text.NumberFormat
import java.util.*

fun euro(v: Double?): String = v?.let {
    val nf = NumberFormat.getCurrencyInstance(Locale.GERMANY)
    nf.currency = Currency.getInstance("EUR")
    nf.format(it)
} ?: "—"

// Format "subtitle" under each product card: "250 g", "1 L • 3.5%" etc.
fun productSubtitle(sizeMlG: Int?, unitKind: String, fatPct: Double?): String {
    val size = sizeMlG?.let {
        when (unitKind.lowercase(Locale.ROOT)) {
            "ml" -> if (it % 1000 == 0) "${it / 1000} L" else "$it ml"
            "g"  -> if (it % 1000 == 0) "${it / 1000} kg" else "$it g"
            else -> "—"
        }
    } ?: "—"

    val pct = fatPct?.let { " • ${trimPct(it)}%" } ?: ""
    return size + pct
}

private fun trimPct(v: Double): String {
    val s = v.toString()
    return if (s.endsWith(".0")) s.dropLast(2) else s
}
