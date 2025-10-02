package com.pricecompare.ui

fun sqName(en: String) = when (en) {
    "Milk 1L 2.8%" -> "Qumësht 1L 2.8%"
    "Milk 1L 3.5%" -> "Qumësht 1L 3.5%"
    "Feta / White Cheese 400g" -> "Djathë i bardhë 400g"
    "Yogurt 1kg tub" -> "Kos 1kg"
    "Butter 250g" -> "Gjalpë 250g"
    "Potatoes per kg" -> "Patate për kg"
    else -> en
}
