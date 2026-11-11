/* Shared loading, retry, and error handling for all inventory searches. */
window.SearchUI = (() => {
    const status = document.getElementById('search-status');
    const errorBox = document.getElementById('search-error');
    const errorText = document.getElementById('search-error-text');
    const retry = document.getElementById('search-retry');
    const button = document.getElementById('search-button');
    const results = document.getElementById('results-list');
    const model = document.getElementById('model');
    let busy = false;

    function message(text, loading = false) {
        status.textContent = text;
        status.hidden = !text;
        status.classList.toggle('is-loading', loading);
    }

    async function json(url) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 180000);
        try {
            const response = await fetch(url, {signal: controller.signal});
            let data;
            try {
                data = await response.json();
            } catch (error) {
                if (error.name === 'AbortError') throw error;
                throw new Error('The server returned an unexpected response. Please try again.');
            }
            if (!response.ok) {
                throw new Error(typeof data?.error === 'string'
                    ? data.error : 'The request failed. Please try again.');
            }
            return data;
        } catch (error) {
            if (error.name === 'AbortError') {
                throw new Error('The request took too long. Please try again.');
            }
            if (error instanceof TypeError) {
                throw new Error('Could not connect to the server. Check your connection and try again.');
            }
            throw error;
        } finally {
            clearTimeout(timeout);
        }
    }

    async function run(url, kind, render) {
        if (busy) return;
        const isSearch = kind === 'search';
        // A placeholder selection needs no model request.
        if (!isSearch && !new URL(url, window.location.href).searchParams.get('make')) {
            model.replaceChildren(new Option('Any model', ''));
            errorBox.hidden = true;
            message('Select a make to load models.');
            return;
        }
        busy = true;
        const controls = [...document.querySelectorAll('#make, #model, #location, #search, #search-button')];
        const disabled = controls.map(control => control.disabled);
        const label = button.textContent;
        controls.forEach(control => { control.disabled = true; });
        button.textContent = isSearch ? 'Searching…' : 'Loading models…';
        errorBox.hidden = true;
        retry.onclick = null;
        message(isSearch ? 'Searching inventory…' : 'Loading models…', true);
        const region = isSearch ? document.getElementById('inventory-results') : model;
        region.setAttribute('aria-busy', 'true');
        if (isSearch) results.replaceChildren();
        else model.replaceChildren(new Option('Any model', ''));
        try {
            const data = await json(url);
            const items = data?.[isSearch ? 'results' : 'models'];
            if (!Array.isArray(items)) {
                throw new Error('The server returned an unexpected response. Please try again.');
            }
            await render(data);
            if (isSearch) {
                message(items.length ? `${items.length} vehicle${items.length === 1 ? '' : 's'} found.`
                    : 'No vehicles found. Try different search criteria.');
            } else {
                if (!model.options.length) model.add(new Option('Any model', ''));
                message(items.length ? 'Models loaded.' : 'No models found. You can search all models for this make.');
            }
        } catch (error) {
            if (isSearch) results.replaceChildren();
            else model.replaceChildren(new Option('Any model', ''));
            message('');
            errorText.textContent = `${isSearch ? 'Could not load inventory.' : 'Could not load models.'} ${error.message || 'Please try again.'}`;
            errorBox.hidden = false;
            retry.onclick = () => run(url, kind, render);
        } finally {
            region.setAttribute('aria-busy', 'false');
            controls.forEach((control, index) => { control.disabled = disabled[index]; });
            button.textContent = label;
            busy = false;
        }
    }

    // A retry belongs to the failed selection; discard it when filters change.
    document.querySelectorAll('#make, #model, #location, #search').forEach(control => {
        control.addEventListener('input', () => {
            if (!busy) {
                errorBox.hidden = true;
                retry.onclick = null;
                message('');
            }
        });
    });
    if (model) model.replaceChildren(new Option('Any model', ''));
    return {run, json};
})();
