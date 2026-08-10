/**
 * Mete el logo de Producción Online dentro de `contenido.json` como data URI,
 * para que el prototipo siga abriéndose sin red.
 *
 *   node docs/rediseno/incrustar-logo.cjs <ruta-al-logo>
 *   node docs/rediseno/construir.cjs        # y se regenera
 *
 * Acepta .svg, .png y .webp.
 *
 * Sobre el color: el logo original es negro sobre blanco y las tarjetas del
 * diagnóstico son oscuras, así que tal cual no se vería. Con un SVG se
 * recolorea aquí mismo a blanco (opción por defecto). Con un PNG no se puede,
 * y hace falta que venga ya en claro y con fondo transparente — si no, se
 * verá un rectángulo blanco alrededor.
 */
const fs = require('fs');
const path = require('path');

const origen = process.argv[2];
if (!origen) {
    console.error('uso: node incrustar-logo.cjs <ruta-al-logo> [--conservar-color]');
    process.exit(2);
}
if (!fs.existsSync(origen)) {
    console.error(`no existe: ${origen}`);
    process.exit(2);
}

const conservar = process.argv.includes('--conservar-color');
const ext = path.extname(origen).toLowerCase();
const destino = path.join(__dirname, 'contenido.json');
const contenido = JSON.parse(fs.readFileSync(destino, 'utf8'));

let dataUri;
if (ext === '.svg') {
    let svg = fs.readFileSync(origen, 'utf8');
    // Producción Online tiene una versión del logo ya en blanco (la _B). Si
    // llega esa, recolorear sobra: se detecta y se deja como está.
    const yaEsClaro = /fill:\s*#(fff|ffffff)\b/i.test(svg) || /fill="#(fff|ffffff)"/i.test(svg);
    if (!conservar && !yaEsClaro) {
        // El monograma en su versión normal viene en negro (#1D1D1B, #000…).
        // Sobre una tarjeta oscura hay que pasarlo a blanco.
        svg = svg
            .replace(/fill="#(0{3,6}|1[dD]1[dD]1[bB]|1a1a1a|111111|222222)"/g, 'fill="#FFFFFF"')
            .replace(/fill:\s*#(0{3,6}|1[dD]1[dD]1[bB])/g, 'fill:#FFFFFF');
        if (!/fill[=:]/.test(svg)) {
            // Sin fill declarado hereda del contenedor: se fuerza en la raíz.
            svg = svg.replace('<svg', '<svg fill="#FFFFFF"');
        }
    }
    dataUri = 'data:image/svg+xml;base64,' + Buffer.from(svg, 'utf8').toString('base64');
    console.log(yaEsClaro ? 'SVG incrustado — ya venía en blanco, no se toca el color'
              : conservar ? 'SVG incrustado sin tocar el color'
                          : 'SVG incrustado y recoloreado a blanco');
} else if (ext === '.png' || ext === '.webp') {
    const mime = ext === '.png' ? 'image/png' : 'image/webp';
    dataUri = `data:${mime};base64,` + fs.readFileSync(origen).toString('base64');
    console.log(`${ext.slice(1).toUpperCase()} incrustado tal cual.`);
    console.log('AVISO: si el logo es oscuro o lleva fondo blanco, no se verá');
    console.log('bien sobre la tarjeta. Para eso hace falta el SVG o un PNG');
    console.log('en claro con transparencia.');
} else {
    console.error(`formato no soportado: ${ext}. Usa .svg, .png o .webp`);
    process.exit(2);
}

contenido.logoPO = dataUri;
fs.writeFileSync(destino, JSON.stringify(contenido, null, 1), 'utf8');
console.log(`contenido.json actualizado — ${Math.round(dataUri.length / 1024)} KB de logo`);
console.log('Ahora: node docs/rediseno/construir.cjs');
