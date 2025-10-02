package com.pricecompare.util

import java.text.NumberFormat
import java.util.*

fun euro(v: Double?): String = v?.let {
    val nf = NumberFormat.getCurrencyInstance(Locale.GERMANY) // uses comma, € suffix
    nf.currency = Currency.getInstance("EUR")
    nf.format(it)
} ?: "—"
