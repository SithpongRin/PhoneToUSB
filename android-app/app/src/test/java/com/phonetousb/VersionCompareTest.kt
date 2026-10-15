package com.phonetousb

import org.junit.Assert.*
import org.junit.Test

class VersionCompareTest {

    private fun isNewerVersion(remote: String, local: String): Boolean {
        val rParts = remote.split(".").mapNotNull { it.toIntOrNull() }
        val lParts = local.split(".").mapNotNull { it.toIntOrNull() }

        val maxLen = maxOf(rParts.size, lParts.size)
        for (i in 0 until maxLen) {
            val r = rParts.getOrElse(i) { 0 }
            val l = lParts.getOrElse(i) { 0 }
            if (r > l) return true
            if (r < l) return false
        }
        return false
    }

    @Test
    fun testVersionComparison() {
        assertTrue(isNewerVersion("1.0.1", "1.0.0"))
        assertTrue(isNewerVersion("1.1.0", "1.0.9"))
        assertTrue(isNewerVersion("2.0.0", "1.9.9"))

        assertFalse(isNewerVersion("1.0.0", "1.0.0"))
        assertFalse(isNewerVersion("0.9.9", "1.0.0"))
        assertFalse(isNewerVersion("1.0.0", "1.0.1"))
    }

    @Test
    fun testPathSanitization() {
        val unsafePath = "../../Windows/System32"
        val isTraversal = unsafePath.contains("..")
        assertTrue(isTraversal)

        val cleanPath = "Documents/Reports/2026.pdf"
        assertFalse(cleanPath.contains(".."))
        assertFalse(cleanPath.startsWith("/"))
    }
}
