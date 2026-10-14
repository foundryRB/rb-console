import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const allowed = {
    atoms: [],
    molecules: ['atoms'],
    organisms: ['atoms', 'molecules', 'organisms'],
    templates: ['organisms'],
    pages: ['atoms', 'molecules', 'organisms', 'templates'],
};

const containsJsx = (node) => {
    if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node) || ts.isJsxFragment(node)) return true;
    return Boolean(ts.forEachChild(node, containsJsx));
};

const componentNames = (source) => {
    const names = [];
    const visit = (node) => {
        if (ts.isFunctionDeclaration(node) && node.name && /^[A-Z]/.test(node.name.text) && containsJsx(node)) names.push(node.name.text);
        if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && /^[A-Z]/.test(node.name.text) && node.initializer && !ts.isJsxElement(node.initializer) && !ts.isJsxSelfClosingElement(node.initializer) && containsJsx(node.initializer)) names.push(node.name.text);
        ts.forEachChild(node, visit);
    };
    visit(source);
    return names;
};

export function checkViews(projectRoot) {
    const root = path.resolve(projectRoot);
    const views = path.join(root, 'src/views');
    const configuration = ts.readConfigFile(path.join(root, 'tsconfig.app.json'), ts.sys.readFile);
    if (configuration.error) throw new Error(ts.flattenDiagnosticMessageText(configuration.error.messageText, '\n'));
    const options = ts.parseJsonConfigFileContent(configuration.config, ts.sys, root).options;
    const files = fs.readdirSync(views, { recursive: true }).filter((name) => name.endsWith('.tsx'));
    const program = ts.createProgram(files.map((name) => path.join(views, name)), options);
    const checker = program.getTypeChecker();
    const issues = [];
    for (const relative of files) {
        const file = path.join(views, relative);
        const level = relative.split(path.sep)[0];
        const source = program.getSourceFile(file);
        const report = (node, message) => issues.push({ file: path.relative(root, file), line: source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1, message });
        if (!(level in allowed)) {
            report(source, 'View components belong to one Atomic level');
            continue;
        }
        const names = componentNames(source);
        if (names.length !== 1 || names[0] !== path.basename(file, '.tsx')) report(source, 'One named component per file; component and filename must match');
        for (const node of source.statements) {
            if (!ts.isImportDeclaration(node) || !ts.isStringLiteral(node.moduleSpecifier)) continue;
            const module = node.moduleSpecifier.text;
            const clause = node.importClause;
            const target = ts.resolveModuleName(module, file, options, ts.sys).resolvedModule?.resolvedFileName;
            const targetRelative = target && path.relative(views, target);
            const targetLevel = targetRelative && !targetRelative.startsWith('..') && !path.isAbsolute(targetRelative) ? targetRelative.split(path.sep)[0] : null;
            const runtime = !clause?.isTypeOnly && (Boolean(clause?.name) || !ts.isNamedImports(clause?.namedBindings ?? {}) || clause.namedBindings.elements.some((item) => !item.isTypeOnly));
            if (runtime && targetLevel && !allowed[level].includes(targetLevel)) report(node, `${level} cannot compose ${targetLevel}`);
            const bindings = ts.isNamedImports(clause?.namedBindings ?? {}) ? clause.namedBindings.elements.filter((item) => !item.isTypeOnly).map((item) => item.propertyName?.text ?? item.name.text) : ['*'];
            const vm = target && path.relative(path.join(root, 'src/viewmodels'), target);
            const fromVm = vm && !vm.startsWith('..') && !path.isAbsolute(vm);
            if (runtime && fromVm && ['atoms', 'molecules', 'templates'].includes(level) && (level === 'templates' || bindings.some((name) => /^use[A-Z]/.test(name) || (name === '*' && !/\.model\.[tj]s$/.test(target))) || /\.(actions|state)\.[tj]s$/.test(target))) report(node, `${level} cannot bind connected ViewModel state`);
            if (level === 'templates' && target && path.relative(path.join(root, 'src/models'), target).split(path.sep)[0] !== '..') report(node, 'Templates receive layout slots, not API model data');
            if (level === 'templates' && module === 'react' && bindings.some((name) => /^use[A-Z]/.test(name))) report(node, 'Templates own layout slots; presentation state belongs in an organism');
            if (runtime && (bindings.includes('apiFetch') || module === 'axios' || module === 'zustand' || module === 'react-redux' || module.includes('/adapters/'))) report(node, 'Views acquire data through ViewModel actions');
        }
        const visit = (node) => {
            if (ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword && ts.isStringLiteral(node.arguments[0])) {
                const target = ts.resolveModuleName(node.arguments[0].text, file, options, ts.sys).resolvedModule?.resolvedFileName;
                if (target) {
                    const origin = path.relative(views, target);
                    if (!origin.startsWith('..') && !path.isAbsolute(origin) && !allowed[level].includes(origin.split(path.sep)[0])) report(node, `${level} cannot lazy-load a higher or same-level component`);
                    const vm = path.relative(path.join(root, 'src/viewmodels'), target);
                    if (!vm.startsWith('..') && !path.isAbsolute(vm) && ['atoms', 'molecules', 'templates'].includes(level) && !/\.model\.[tj]s$/.test(vm)) report(node, `${level} cannot lazy-load connected ViewModel state`);
                }
            }
            if (ts.isCallExpression(node) && (ts.isIdentifier(node.expression) ? node.expression.text === 'fetch' : ts.isPropertyAccessExpression(node.expression) && node.expression.name.text === 'fetch')) report(node, 'Views cannot perform HTTP I/O');
            if (ts.isNewExpression(node) && ts.isIdentifier(node.expression) && ['WebSocket', 'XMLHttpRequest', 'EventSource'].includes(node.expression.text)) report(node, 'Views cannot create network transports');
            if (ts.isCallExpression(node) && ['atoms', 'molecules', 'templates'].includes(level)) {
                const expressions = [node.expression];
                if (ts.isPropertyAccessExpression(node.expression)) expressions.push(node.expression.expression);
                for (const expression of expressions) {
                    const symbol = checker.getSymbolAtLocation(expression);
                    const original = symbol?.flags & ts.SymbolFlags.Alias ? checker.getAliasedSymbol(symbol) : symbol;
                    for (const declaration of original?.declarations ?? []) {
                        const origin = path.relative(path.join(root, 'src/viewmodels'), declaration.getSourceFile().fileName);
                        if (!origin.startsWith('..') && !path.isAbsolute(origin) && /\.(actions|state)\.[tj]s$/.test(origin)) report(node, `${level} cannot call connected state through an alias or barrel`);
                    }
                }
            }
            if ((ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) && level !== 'organisms' && ts.isIdentifier(node.tagName) && names.includes(node.tagName.text)) report(node, 'Same-level recursive composition belongs in an organism');
            if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
                const symbol = checker.getSymbolAtLocation(node.tagName);
                const original = symbol?.flags & ts.SymbolFlags.Alias ? checker.getAliasedSymbol(symbol) : symbol;
                for (const declaration of original?.declarations ?? []) {
                    if (path.resolve(declaration.getSourceFile().fileName) === path.resolve(file) && ts.isVariableDeclaration(declaration) && !names.includes(declaration.name.getText(source))) continue;
                    const origin = path.relative(views, declaration.getSourceFile().fileName);
                    if (origin.startsWith('..') || path.isAbsolute(origin)) continue;
                    const owner = origin.split(path.sep)[0];
                    if (!allowed[level].includes(owner)) report(node, `${level} cannot render ${owner} through an alias or barrel`);
                }
            }
            ts.forEachChild(node, visit);
        };
        visit(source);
    }
    return { files: files.length, issues };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
    const result = checkViews(process.cwd());
    for (const issue of result.issues) console.error(`${issue.file}:${issue.line}: ${issue.message}`);
    if (result.issues.length) process.exitCode = 1;
    else console.log(`View boundaries passed (${result.files} components)`);
}
