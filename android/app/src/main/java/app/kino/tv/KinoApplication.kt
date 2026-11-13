package app.kino.tv

import android.app.Application
import coil.ImageLoader
import coil.ImageLoaderFactory
import coil.disk.DiskCache
import coil.memory.MemoryCache

class KinoApplication : Application(), ImageLoaderFactory {
    override fun onCreate() {
        super.onCreate()
        Marks.app = this
    }

    override fun newImageLoader(): ImageLoader = ImageLoader.Builder(this)
        .allowRgb565(true)
        .memoryCache { MemoryCache.Builder(this).maxSizePercent(0.12).build() }
        .diskCache { DiskCache.Builder().directory(cacheDir.resolve("img")).maxSizeBytes(100L * 1024 * 1024).build() }
        .build()
}
