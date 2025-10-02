package com.pricecompare.di

import com.pricecompare.data.Repo
import com.pricecompare.data.remote.ApiService

object AppModule {
    private const val BASE_URL = "http://10.0.2.2:8000/"
    val api: ApiService by lazy { ApiService.create(BASE_URL) }
    val repo: Repo by lazy { Repo(api) }
}
