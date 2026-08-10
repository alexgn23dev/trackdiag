/**
 * Ejecuta los componentes del prototipo en Node y comprueba que renderizan.
 *
 *   SCRATCH=<dir con vendor/> node docs/rediseno/verificar.cjs
 *
 * No sustituye a mirar la página con los ojos, pero sí atrapa lo que de
 * verdad rompe un prototipo con datos reales: un `undefined.toFixed()`, un
 * `.map` sobre un campo que en ese análisis no existe, un `.split` sobre null.
 * Esos fallos dejan la página en blanco y no se ven hasta que se abre.
 *
 * Se renderiza CADA pestaña con CADA uno de los tres análisis de ejemplo:
 * un boceto, un máster caliente y un track cuidado. Son los que tienen
 * campos distintos rellenos.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const DIR = __dirname;
const SCRATCH = process.env.SCRATCH;
if (!SCRATCH) { console.error('falta SCRATCH=<dir con vendor/>'); process.exit(2); }

const html = fs.readFileSync(path.join(DIR, 'prototipo.html'), 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
if (scripts.length < 3) { console.error('no se encontraron los tres <script>'); process.exit(2); }
const codigoComponentes = scripts[scripts.length - 1];

// Entorno mínimo: React y ReactDOMServer, más un ReactDOM falso para que la
// última línea (createRoot(...).render) no intente tocar el DOM.
const sandbox = { console, setTimeout, clearTimeout, TextEncoder, TextDecoder,
                  Uint8Array, ArrayBuffer, Promise, Map, Set, JSON, Math, Object,
                  Array, String, Number, Boolean, Error, RegExp, Date, Symbol };
sandbox.window = sandbox;
sandbox.self = sandbox;
sandbox.globalThis = sandbox;
sandbox.document = { getElementById: () => ({}) };
vm.createContext(sandbox);

// React se carga desde node_modules (no el UMD de navegador) porque el build
// UMD de react-dom/server solo expone streams, y aquí interesa el marcado
// sincrónico. Es el mismo React 18: lo que se verifica es MI código, no el suyo.
const React = require(path.join(SCRATCH, 'node_modules', 'react'));
const Server = require(path.join(SCRATCH, 'node_modules', 'react-dom', 'server'));
sandbox.React = React;
sandbox.ReactDOM = { createRoot: () => ({ render: () => {} }) };

// Ojo: en un contexto de vm, un `const` de nivel superior NO se cuelga del
// objeto global (solo lo hacen `var` y las declaraciones de función). Por eso
// se añade un epílogo que exporta explícitamente lo que hace falta.
const epilogo = `
;globalThis.__proto = { CASOS, CONTENIDO, TABS, Diagnostico,
    TabResumen, TabPlan, TabMezcla, TabMaster, TabDetalle };`;
vm.runInContext(codigoComponentes + epilogo, sandbox, { filename: 'prototipo.js' });

const P = sandbox.__proto;
const CASOS = P.CASOS;
const TABS = P.TABS.map(t => t.id);
const COMPONENTES = {
    resumen: P.TabResumen, plan: P.TabPlan, mezcla: P.TabMezcla,
    master: P.TabMaster, detalle: P.TabDetalle,
};

let fallos = 0;
console.log(`Análisis de ejemplo: ${Object.keys(CASOS).join(', ')}\n`);

// Cabecera y armazón completo
for (const [clave, caso] of Object.entries(CASOS)) {
    try {
        const out = Server.renderToStaticMarkup(React.createElement(P.Diagnostico, { r: caso.resultado }));
        const texto = out.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
        console.log(`  Diagnostico(${clave}): OK · ${Math.round(out.length / 1024)} KB de marcado, ${texto.length} caracteres visibles`);
        if (texto.includes('undefined') || texto.includes('NaN')) {
            console.error(`    ✗ el texto visible contiene "undefined" o "NaN"`);
            fallos++;
        }
    } catch (e) {
        console.error(`  Diagnostico(${clave}): FALLA — ${e.message}`);
        fallos++;
    }
}

console.log('');
for (const tab of TABS) {
    for (const [clave, caso] of Object.entries(CASOS)) {
        try {
            const out = Server.renderToStaticMarkup(
                React.createElement(COMPONENTES[tab], { r: caso.resultado }));
            const texto = out.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
            const sospechoso = /undefined|NaN|\[object Object\]/.test(texto);
            console.log(`  ${tab.padEnd(9)} ${clave.padEnd(9)} ${sospechoso ? '✗' : 'OK'} · ${texto.length} caracteres`);
            if (sospechoso) {
                fallos++;
                const m = texto.match(/.{0,60}(undefined|NaN|\[object Object\]).{0,60}/);
                console.error(`      → «…${m[0]}…»`);
            }
        } catch (e) {
            console.error(`  ${tab.padEnd(9)} ${clave.padEnd(9)} FALLA — ${e.message}`);
            fallos++;
        }
    }
}

// ---------------------------------------------------------------------------
// La fila de abajo del resumen: CTA siempre, tutoriales solo si los hay.
// ---------------------------------------------------------------------------
console.log('\nFila de siguiente paso / tutoriales / calibración:');
const base = JSON.parse(JSON.stringify(Object.values(CASOS)[0].resultado));
const conTutoriales = Object.keys(P.CONTENIDO.tutoriales);
const casosFila = [
    ['con tutoriales', conTutoriales[0], 3],
    ['sin tutoriales', 'categoria_sin_tutoriales_de_prueba', 2],
];
for (const [etiqueta, dxId, columnasEsperadas] of casosFila) {
    const r = JSON.parse(JSON.stringify(base));
    r.diagnostico_principal.id = dxId;
    delete r.diagnostico_secundario;
    const out = Server.renderToStaticMarkup(React.createElement(P.TabResumen, { r }));
    const m = out.match(/class="[^"]*pt-1[^"]*"/);
    const cols = m && m[0].includes('grid-cols-3') ? 3 : m && m[0].includes('grid-cols-2') ? 2 : 0;
    const cta = out.includes('Ver el programa');
    const ok = cols === columnasEsperadas && cta;
    if (!ok) fallos++;
    console.log(`  ${etiqueta.padEnd(16)} ${ok ? 'OK' : '✗'} · columnas=${cols} (esperadas ${columnasEsperadas}) · CTA=${cta ? 'sí' : 'NO'}`);
}

console.log(fallos ? `\n${fallos} problema(s).` : '\nTodo renderiza sin errores ni huecos.');
process.exit(fallos ? 1 : 0);
