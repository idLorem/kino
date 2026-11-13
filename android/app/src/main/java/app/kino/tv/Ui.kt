package app.kino.tv

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.zIndex
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalConfiguration
import coil.compose.AsyncImage

object C {
    val bg = Color(0xFF060606)
    val text = Color(0xFFF2F2F2)
    val muted = Color(0x85F2F2F2)
    val stroke = Color(0x1AFFFFFF)
    val glass = Color(0x0FFFFFFF)
    val good = Color(0xFF9AD4AE)
    val mid = Color(0xFFC9C9C9)
    val bad = Color(0xFFE29A9A)
    val white = Color(0xFFEDEDED)
    val ink = Color(0xFF0A0A0A)
}

fun ratingColor(r: Double): Color = when {
    r >= 7.0 -> C.good
    r >= 5.5 -> C.mid
    else -> C.bad
}

@Composable
fun Pill(
    label: String,
    selected: Boolean = false,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    radius: Dp = 12.dp,
    focusRequester: FocusRequester? = null,
    hPad: Dp = 22.dp,
    leading: (@Composable (Color) -> Unit)? = null,
) {
    var focused by remember { mutableStateOf(false) }
    var widthPx by remember { mutableStateOf(0) }
    val growPx = with(androidx.compose.ui.platform.LocalDensity.current) { 12.dp.toPx() }
    val shape = RoundedCornerShape(radius)
    val bgc = when {
        selected -> C.white
        focused -> Color(0x33FFFFFF)
        else -> C.glass
    }
    val fg = if (selected) C.ink else C.text
    Box(
        modifier = modifier
            .onSizeChanged { widthPx = it.width }
            .graphicsLayer {
                val s = if (focused && widthPx > 0) 1f + minOf(0.06f, growPx / widthPx) else 1f
                scaleX = s
                scaleY = s
            }
            .clip(shape)
            .background(bgc)
            .border(if (focused) 3.dp else 1.dp, if (focused) C.text else C.stroke, shape)
            .then(if (focusRequester != null) Modifier.focusRequester(focusRequester) else Modifier)
            .onFocusChanged { focused = it.isFocused }
            .clickable { onClick() }
            .padding(horizontal = hPad, vertical = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        if (leading != null) {
            androidx.compose.foundation.layout.Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(8.dp),
            ) {
                leading(fg)
                if (label.isNotEmpty()) Text(label, color = fg, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
            }
        } else {
            Text(label, color = fg, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
        }
    }
}

@Composable
fun BackArrow(color: Color) {
    Canvas(Modifier.size(16.dp)) {
        val w = size.width
        val h = size.height
        val sw = 2.dp.toPx()
        val cy = h / 2f
        drawLine(color, Offset(w * 0.92f, cy), Offset(w * 0.10f, cy), strokeWidth = sw, cap = StrokeCap.Round)
        drawLine(color, Offset(w * 0.10f, cy), Offset(w * 0.46f, cy - w * 0.36f), strokeWidth = sw, cap = StrokeCap.Round)
        drawLine(color, Offset(w * 0.10f, cy), Offset(w * 0.46f, cy + w * 0.36f), strokeWidth = sw, cap = StrokeCap.Round)
    }
}

@Composable
fun PlayGlyph(color: Color, size: Dp) {
    Canvas(Modifier.size(size)) {
        val w = this.size.width
        val p = Path()
        p.moveTo(w * 0.22f, w * 0.10f)
        p.lineTo(w * 0.92f, w * 0.50f)
        p.lineTo(w * 0.22f, w * 0.90f)
        p.close()
        drawPath(p, color)
    }
}

@Composable
fun PauseGlyph(color: Color, size: Dp) {
    Canvas(Modifier.size(size)) {
        val w = this.size.width
        val bw = w * 0.26f
        drawRect(color, Offset(w * 0.16f, w * 0.10f), androidx.compose.ui.geometry.Size(bw, w * 0.80f))
        drawRect(color, Offset(w * 0.58f, w * 0.10f), androidx.compose.ui.geometry.Size(bw, w * 0.80f))
    }
}

@Composable
fun PinIcon(color: Color, size: Dp) {
    Canvas(Modifier.size(size)) {
        val w = this.size.width
        val sw = w * 0.11f
        val p = Path()
        p.moveTo(w * 0.36f, w * 0.12f)
        p.lineTo(w * 0.64f, w * 0.12f)
        p.lineTo(w * 0.60f, w * 0.40f)
        p.lineTo(w * 0.76f, w * 0.56f)
        p.lineTo(w * 0.24f, w * 0.56f)
        p.lineTo(w * 0.40f, w * 0.40f)
        p.close()
        drawPath(p, color, style = Stroke(width = sw, cap = StrokeCap.Round))
        drawLine(color, Offset(w * 0.5f, w * 0.56f), Offset(w * 0.5f, w * 0.90f), strokeWidth = sw, cap = StrokeCap.Round)
    }
}

@Composable
fun Chip(text: String, color: Color = C.text, modifier: Modifier = Modifier) {
    Box(
        modifier
            .clip(RoundedCornerShape(8.dp))
            .background(Color(0xB3000000))
            .padding(horizontal = 8.dp, vertical = 3.dp),
    ) {
        Text(text, color = color, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
    }
}

@Composable
fun PosterImage(item: Item, conn: Conn, modifier: Modifier = Modifier) {
    val p = item.poster
    val remote = p?.takeIf { it.startsWith("http") }
    val urls = listOfNotNull(
        remote?.let { conn.imgUrl(it) },
        conn.posterUrl(item.id),
        remote,
    )
    var idx by remember(item.id, p) { mutableStateOf(0) }
    val url = urls.getOrNull(idx)
    Box(modifier.background(Color(0xFF111111))) {
        if (url != null) {
            AsyncImage(
                model = url,
                contentDescription = null,
                contentScale = ContentScale.Crop,
                onError = { idx++ },
                modifier = Modifier.fillMaxSize(),
            )
        } else {
            Text(
                item.title,
                color = C.muted,
                fontSize = 14.sp,
                modifier = Modifier.align(Alignment.Center).padding(12.dp),
                maxLines = 4,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
@OptIn(ExperimentalFoundationApi::class)
fun PosterCard(item: Item, conn: Conn, onClick: () -> Unit, modifier: Modifier = Modifier, focusRequester: FocusRequester? = null, onLongClick: (() -> Unit)? = null) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(16.dp)
    Box(
        modifier
            .clip(shape)
            .border(if (focused) 3.dp else 1.dp, if (focused) C.text else Color(0x21FFFFFF), shape)
            .then(if (focusRequester != null) Modifier.focusRequester(focusRequester) else Modifier)
            .onFocusChanged { focused = it.isFocused }
            .combinedClickable(onClick = { onClick() }, onLongClick = onLongClick),
    ) {
        PosterImage(item, conn, Modifier.fillMaxSize())
        Box(
            Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .background(Brush.verticalGradient(listOf(Color(0x00000000), Color(0xE6000000))))
                .padding(start = 12.dp, end = 12.dp, top = 36.dp, bottom = 10.dp),
        ) {
            Column {
                Text(
                    item.title,
                    color = C.text,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                val sub = listOfNotNull(
                    if (item.year > 0) item.year.toString() else null,
                    if (item.duration > 0) "${item.duration} " + tr("мин", "min") else null,
                ).joinToString(" · ")
                if (sub.isNotEmpty()) Text(sub, color = C.muted, fontSize = 13.sp, maxLines = 1)
            }
        }
        if (item.progress > 0f) {
            Box(Modifier.align(Alignment.BottomCenter).fillMaxWidth().height(5.dp).background(Color(0x66000000))) {
                Box(Modifier.fillMaxHeight().fillMaxWidth(item.progress).background(C.white))
            }
        }
        if (item.series) {
            Chip(
                tr("Сериал", "Series"),
                modifier = Modifier.align(Alignment.TopStart).padding(8.dp),
            )
        }
        Box(Modifier.align(Alignment.TopEnd).padding(8.dp)) {
            if (item.pinned > 0) {
                Box(
                    Modifier
                        .size(26.dp)
                        .clip(RoundedCornerShape(9.dp))
                        .background(Color(0xB3000000))
                        .padding(4.dp),
                ) { PinIcon(C.text, 18.dp) }
            } else if (item.ratingText.isNotEmpty()) {
                Chip(item.ratingText, ratingColor(item.rating))
            }
        }
        if (item.pinned > 0 && item.ratingText.isNotEmpty()) {
            Chip(
                item.ratingText,
                ratingColor(item.rating),
                Modifier.align(Alignment.TopEnd).padding(top = 8.dp, end = 42.dp),
            )
        }
    }
}

@Composable
fun BackPill(onBack: () -> Unit, modifier: Modifier = Modifier) {
    Pill(tr("Назад", "Back"), onClick = onBack, modifier = modifier, hPad = 18.dp, leading = { BackArrow(it) })
}

@Composable
fun compact(): Boolean = LocalConfiguration.current.let { it.screenWidthDp < 700 || it.screenHeightDp < 480 }

val SUB_SIZES = listOf("s", "m", "l")
val SUB_POS = listOf("0", "1", "2", "3")
val SUB_BG = listOf("0", "50", "75", "100")

fun subSizeLabel(v: String): String = when (v) { "s" -> tr("Мелкий", "Small"); "l" -> tr("Крупный", "Large"); else -> tr("Средний", "Medium") }
fun subPosLabel(v: String): String = when (v) { "0" -> tr("Низко", "Low"); "2" -> tr("Выше", "Higher"); "3" -> tr("Высоко", "High"); else -> tr("Обычно", "Normal") }
fun subBgLabel(v: String): String = "$v%"

fun nextOf(cur: String, all: List<String>): String = all[(all.indexOf(cur) + 1) % all.size]
