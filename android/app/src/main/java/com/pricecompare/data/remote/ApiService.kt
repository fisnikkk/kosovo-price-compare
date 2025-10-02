package com.pricecompare.data.remote

import retrofit2.http.GET
import retrofit2.http.Query
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory

interface ApiService {
    @GET("products")
    suspend fun listProducts(): List<Product>

    @GET("products/search")
    suspend fun searchProducts(@Query("q") q: String): List<Product>

    @GET("compare")
    suspend fun compare(@Query("product_id") productId: Int): CompareOut

        companion object {
            fun create(baseUrl: String): ApiService {
                val log = HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BASIC }
                val client = OkHttpClient.Builder().addInterceptor(log).build()

                val moshi = Moshi.Builder()
                    .add(KotlinJsonAdapterFactory())   // <-- important
                    .build()

                return Retrofit.Builder()
                    .baseUrl(baseUrl)
                    .client(client)
                    .addConverterFactory(MoshiConverterFactory.create(moshi)) // <-- use our Moshi
                    .build()
                    .create(ApiService::class.java)
            }
        }
}
