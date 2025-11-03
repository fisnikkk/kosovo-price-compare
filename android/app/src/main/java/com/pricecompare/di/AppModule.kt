package com.pricecompare.di

import com.pricecompare.data.Repo
import com.pricecompare.data.remote.ApiService

object AppModule {
    // Change to your backend’s base URL (with trailing slash)
    private const val BASE_URL = "http://10.0.2.2:8000/"

    private val api: ApiService by lazy { ApiService.build(BASE_URL) }
    val repo: Repo by lazy { Repo(api) }
}
