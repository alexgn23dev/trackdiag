/**
 * Compila el JSX de una SPA single-file igual que lo hace Babel standalone en
 * el navegador.
 *
 * Por qué existe: `index.html` no tiene build step — el JSX se transforma en
 * el cliente. Eso significa que un error de sintaxis NO se detecta al
 * desplegar: se detecta cuando un usuario abre la página y ve una pantalla en
 * blanco. Los tests de Python comprueban que ciertas cadenas están presentes,
 * pero no que el archivo compile.
 *
 *   node frontend/verificar_jsx.js frontend/index.html
 *
 * Requiere @babel/standalone, que es el mismo paquete que carga la página por
 * CDN. Se instala solo en CI; no es una dependencia del proyecto.
 */
const fs = require('fs');
const path = require('path');

function cargarBabel() {
    try {
        return require('@babel/standalone');
    } catch (e) {
        const local = path.join(__dirname, '..', 'node_modules', '@babel', 'standalone');
        return require(local);
    }
}

const archivos = process.argv.slice(2);
if (archivos.length === 0) {
    console.error('uso: node verificar_jsx.js <archivo.html> [...]');
    process.exit(2);
}

const Babel = cargarBabel();
let fallos = 0;

for (const ruta of archivos) {
    const html = fs.readFileSync(ruta, 'utf8');
    const re = /<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/g;
    let m, n = 0;
    while ((m = re.exec(html)) !== null) {
        n++;
        try {
            Babel.transform(m[1], { presets: ['react'], filename: `${ruta}#${n}.jsx` });
            console.log(`  ${ruta} bloque ${n}: OK (${m[1].length.toLocaleString()} chars)`);
        } catch (e) {
            console.error(`  ${ruta} bloque ${n}: FALLA`);
            console.error(`    ${e.message.split('\n')[0]}`);
            fallos++;
        }
    }
    if (n === 0) {
        // No es un aviso menor: si el patrón deja de encontrar nada, este
        // script pasaría siempre y no protegería de nada.
        console.error(`  ${ruta}: no se encontró ningún <script type="text/babel">`);
        fallos++;
    }
}

process.exit(fallos ? 1 : 0);
