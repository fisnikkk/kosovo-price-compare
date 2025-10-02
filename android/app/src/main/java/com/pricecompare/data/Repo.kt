package com.pricecompare.data

import com.pricecompare.data.remote.*

class Repo(private val api: ApiService) {
    suspend fun listProducts() = api.listProducts()
    suspend fun search(q: String) = api.searchProducts(q)
    suspend fun compare(productId: Int) = api.compare(productId)
}
