package com.pricecompare.data

import com.pricecompare.data.remote.ApiService
import com.pricecompare.data.remote.Product
import com.pricecompare.data.remote.CompareOut

class Repo(private val api: ApiService) {
    suspend fun popular(): List<Product> = api.popularProducts()
    suspend fun listProducts(): List<Product> = api.listProducts()
    suspend fun compare(id: Int): CompareOut = api.compare(id)

    // ADD THIS FUNCTION
    suspend fun getAllProducts(): List<Product> {
        // It just needs to call your existing listProducts() function
        return api.listProducts()
    }
}