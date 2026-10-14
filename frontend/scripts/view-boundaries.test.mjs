import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { checkViews } from './view-boundaries.mjs';

function fixture(files, inspect) {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'view-boundaries-'));
    try {
        fs.writeFileSync(path.join(root, 'tsconfig.app.json'), JSON.stringify({ compilerOptions: { moduleResolution: 'bundler', paths: { '@/*': ['./src/*'] } }, include: ['src'] }));
        for (const [name, content] of Object.entries(files)) {
            const file = path.join(root, 'src', name);
            fs.mkdirSync(path.dirname(file), { recursive: true });
            fs.writeFileSync(file, content);
        }
        inspect(checkViews(root).issues.map((issue) => issue.message));
    } finally {
        assert.ok(root.startsWith(path.resolve(os.tmpdir()) + path.sep));
        fs.rmSync(root, { recursive: true, force: true });
    }
}

test('aliases resolve to the actual Atomic owner', () => fixture({
    'views/atoms/Label.tsx': 'import { Panel as Other } from "@/views/molecules/Panel"; export const Label = () => <Other />;',
    'views/molecules/Panel.tsx': 'export const Panel = () => <div />;',
}, (issues) => assert.ok(issues.includes('atoms cannot compose molecules'))));

test('relative namespace imports cannot hide same-level molecule nesting', () => fixture({
    'views/molecules/Panel.tsx': 'import * as UI from "./Bar"; export const Panel = () => <UI.Bar />;',
    'views/molecules/Bar.tsx': 'export const Bar = () => <div />;',
}, (issues) => assert.ok(issues.includes('molecules cannot compose molecules'))));

test('a barrel cannot change the owner of the rendered component', () => fixture({
    'views/atoms/index.ts': 'export { Panel } from "../organisms/Panel";',
    'views/molecules/Group.tsx': 'import { Panel as Content } from "../atoms"; export const Group = () => <Content />;',
    'views/organisms/Panel.tsx': 'export const Panel = () => <section />;',
}, (issues) => assert.ok(issues.includes('molecules cannot render organisms through an alias or barrel'))));

test('connected hook aliases are blocked below organisms while pure model selectors are allowed', () => fixture({
    'viewmodels/feature/feature.actions.ts': 'export const useFeature = () => ({});',
    'viewmodels/feature/feature.model.ts': 'export const label = () => "ready";',
    'views/molecules/Panel.tsx': 'import { useFeature as connected } from "@/viewmodels/feature/feature.actions"; export const Panel = () => <div>{connected()}</div>;',
    'views/atoms/Label.tsx': 'import { useState } from "react"; import { label } from "@/viewmodels/feature/feature.model"; export const Label = () => { const [shown] = useState(true); return <span>{shown && label()}</span>; };',
}, (issues) => {
    assert.ok(issues.includes('molecules cannot bind connected ViewModel state'));
    assert.ok(!issues.some((issue) => issue.startsWith('atoms')));
}));

test('a model barrel cannot turn a connected hook into a pure selector', () => fixture({
    'viewmodels/feature/feature.actions.ts': 'export const useFeature = () => ({});',
    'viewmodels/feature/feature.model.ts': 'export { useFeature as read } from "./feature.actions";',
    'views/molecules/Panel.tsx': 'import { read } from "@/viewmodels/feature/feature.model"; export const Panel = () => <div>{read()}</div>;',
}, (issues) => assert.ok(issues.includes('molecules cannot call connected state through an alias or barrel'))));

test('organisms compose organisms and templates position organisms', () => fixture({
    'views/organisms/Panel.tsx': 'import { Header } from "./Header"; export const Panel = () => <Header />;',
    'views/organisms/Header.tsx': 'export const Header = () => <header />;',
    'views/templates/Layout.tsx': 'import { Panel } from "../organisms/Panel"; export const Layout = () => <main><Panel /></main>;',
}, (issues) => assert.deepEqual(issues, [])));

test('API calls and model-filled templates cross the View boundary', () => fixture({
    'models/index.ts': 'export type State = {};',
    'viewmodels/requests/requests.actions.ts': 'export const apiFetch = () => ({});',
    'views/organisms/Panel.tsx': 'import { apiFetch as request } from "@/viewmodels/requests/requests.actions"; export const Panel = () => <div>{request()}</div>;',
    'views/templates/Layout.tsx': 'import type { State } from "@/models"; export const Layout = (_props: State) => <main />;',
    'views/pages/Page.tsx': 'export const Page = () => { fetch("/api/state"); return <main />; };',
}, (issues) => {
    assert.ok(issues.includes('Views acquire data through ViewModel actions'));
    assert.ok(issues.includes('Templates receive layout slots, not API model data'));
    assert.ok(issues.includes('Views cannot perform HTTP I/O'));
}));

test('one-component ownership and recursive molecule composition are checked', () => fixture({
    'views/atoms/Label.tsx': 'export const Label = () => <span />; const Extra = () => <div />;',
    'views/molecules/Tree.tsx': 'export const Tree = () => <Tree />;',
}, (issues) => {
    assert.ok(issues.includes('One named component per file; component and filename must match'));
    assert.ok(issues.includes('Same-level recursive composition belongs in an organism'));
}));
