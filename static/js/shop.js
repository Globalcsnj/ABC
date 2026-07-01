// Client-side cart stored in localStorage. Items are item_numbers with a qty.
const CART_KEY = 'abc_cart';

function getCart() {
    try { return JSON.parse(localStorage.getItem(CART_KEY)) || {}; }
    catch { return {}; }
}
function saveCart(cart) {
    localStorage.setItem(CART_KEY, JSON.stringify(cart));
    updateCartCount();
}
function updateCartCount() {
    const cart = getCart();
    const n = Object.values(cart).reduce((s, q) => s + q, 0);
    document.querySelectorAll('#cartCount').forEach(el => el.textContent = n);
}
function addToCart(code) {
    const cart = getCart();
    cart[code] = (cart[code] || 0) + 1;
    saveCart(cart);
    flashAdded();
}
function setQty(code, qty) {
    const cart = getCart();
    if (qty <= 0) delete cart[code];
    else cart[code] = qty;
    saveCart(cart);
    renderCart();
}
function flashAdded() {
    let t = document.getElementById('cartToast');
    if (!t) {
        t = document.createElement('div');
        t.id = 'cartToast';
        t.className = 'cart-toast';
        t.textContent = '✓ Added to cart';
        document.body.appendChild(t);
    }
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 1500);
}

async function renderCart() {
    updateCartCount();
    const cart = getCart();
    const codes = Object.keys(cart);
    const empty = document.getElementById('cartEmpty');
    const content = document.getElementById('cartContent');
    if (!empty || !content) return;

    if (!codes.length) {
        empty.style.display = 'block';
        content.style.display = 'none';
        return;
    }
    empty.style.display = 'none';
    content.style.display = 'block';

    const res = await fetch('/api/shop/items?codes=' + encodeURIComponent(codes.join(',')));
    const items = await res.json();
    const box = document.getElementById('cartItems');
    box.innerHTML = items.map(p => {
        const qty = cart[p.item_number] || 1;
        const price = p.retail_price != null ? '$' + Number(p.retail_price).toFixed(2) : 'Ask in store';
        const img = p.photo ? `<img src="/uploads/${p.photo}">` : '<div class="prod-noimg">📦</div>';
        return `<div class="cart-row">
            <div class="cart-thumb">${img}</div>
            <div class="cart-detail">
                <div class="cart-name">${p.description || 'Item'}</div>
                <div class="cart-cat">${p.category || ''}</div>
                <div class="cart-price">${price}</div>
            </div>
            <div class="cart-qty">
                <button onclick="setQty('${p.item_number}', ${qty - 1})">−</button>
                <span>${qty}</span>
                <button onclick="setQty('${p.item_number}', ${qty + 1})">+</button>
                <button class="cart-remove" onclick="setQty('${p.item_number}', 0)">Remove</button>
            </div>
        </div>`;
    }).join('');
}

document.addEventListener('DOMContentLoaded', () => {
    updateCartCount();
    const form = document.getElementById('holdForm');
    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const cart = getCart();
            const data = new FormData(form);
            data.append('items', JSON.stringify(cart));
            const res = await fetch('/api/shop/inquiry', { method: 'POST', body: data });
            const json = await res.json().catch(() => ({}));
            const el = document.getElementById('holdResult');
            if (res.ok && json.id) {
                localStorage.removeItem(CART_KEY);
                window.location.href = '/hold/' + json.id;
            } else {
                el.className = 'import-result error';
                el.textContent = 'Something went wrong. Please try again.';
            }
        });
    }
});
