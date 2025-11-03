package com.pricecompare.data.remote

import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class Product(
    val id: Int,
    val canonical_name: String,
    val category: String,
    val unit: String,           // "g" or "ml" (base-kind, not kg/L)
    val brand: String?,
    val size_ml_g: Int?,        // base units only
    val fat_pct: Double?
)

@JsonClass(generateAdapter = true)
data class PriceOut(
    val store: String,
    val raw_name: String,
    val url: String?,
    val price_eur: Double?,
    val unit_price: Double?,    // €/kg or €/L, already normalized by backend
    val currency: String?,
    val collected_at: String?,
    val promo: Boolean,
    val promo_valid_from: String?,
    val promo_valid_to: String?
)

@JsonClass(generateAdapter = true)
data class CompareOut(
    val product: Product,
    val offers: List<PriceOut>
)
