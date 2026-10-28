/**
 * ReFind — Smart Campus Lost & Found System
 * Editorial Minimalism Client-Side Interactivity & Subtle Motion:
 *   - Sticky header scroll elevation
 *   - Subtle scroll-reveal entrance animations (respecting prefers-reduced-motion)
 *   - Drag-and-drop & file-picker live image preview with client-side size/type validation
 *   - Submit button loading states to prevent duplicate form submissions
 *   - Quick demo credential autofill on the login screen for DBMS viva demonstrations
 *   - Accessible aria-invalid synchronization with native :user-invalid state
 */

document.addEventListener("DOMContentLoaded", () => {
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // 1. Sticky Header Scroll State
    const navbar = document.querySelector(".navbar");
    if (navbar) {
        const updateHeaderScroll = () => {
            if (window.scrollY > 14) {
                navbar.classList.add("scrolled");
            } else {
                navbar.classList.remove("scrolled");
            }
        };
        updateHeaderScroll();
        window.addEventListener("scroll", updateHeaderScroll, { passive: true });
    }

    // 2. Subtle Scroll-Reveal Animations
    const revealNodes = document.querySelectorAll("[data-reveal]");
    if (revealNodes.length > 0) {
        if (prefersReducedMotion || !("IntersectionObserver" in window)) {
            revealNodes.forEach((node) => node.classList.add("revealed"));
        } else {
            const observer = new IntersectionObserver(
                (entries, obs) => {
                    entries.forEach((entry) => {
                        if (entry.isIntersecting) {
                            entry.target.classList.add("revealed");
                            obs.unobserve(entry.target);
                        }
                    });
                },
                { threshold: 0.08, rootMargin: "0px 0px -30px 0px" }
            );
            revealNodes.forEach((node) => observer.observe(node));
        }
    }

    // 3. Image Upload Drag-and-Drop + Live Preview
    const dropzones = document.querySelectorAll("[data-upload-dropzone]");
    dropzones.forEach((zone) => {
        const fileInput = zone.querySelector("input[type='file']");
        const previewContainer = document.querySelector(zone.dataset.previewTarget);
        const previewImg = previewContainer ? previewContainer.querySelector("img") : null;
        const previewLabel = previewContainer ? previewContainer.querySelector("[data-preview-name]") : null;
        const errorLabel = zone.parentElement.querySelector("[data-upload-error]");

        if (!fileInput) return;

        zone.addEventListener("click", (e) => {
            if (e.target.tagName !== "INPUT") {
                fileInput.click();
            }
        });

        zone.addEventListener("dragover", (e) => {
            e.preventDefault();
            zone.classList.add("dragover");
        });

        zone.addEventListener("dragleave", () => {
            zone.classList.remove("dragover");
        });

        zone.addEventListener("drop", (e) => {
            e.preventDefault();
            zone.classList.remove("dragover");
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                fileInput.files = e.dataTransfer.files;
                handleFilePreview(fileInput.files[0]);
            }
        });

        fileInput.addEventListener("change", () => {
            if (fileInput.files && fileInput.files.length > 0) {
                handleFilePreview(fileInput.files[0]);
            }
        });

        function handleFilePreview(file) {
            if (errorLabel) errorLabel.textContent = "";
            const allowedTypes = ["image/png", "image/jpeg", "image/webp"];
            if (!allowedTypes.includes(file.type)) {
                if (errorLabel) {
                    errorLabel.textContent = "Unsupported file format. Please choose a PNG, JPG, or WEBP image.";
                }
                fileInput.value = "";
                if (previewContainer) previewContainer.classList.remove("visible");
                return;
            }
            if (file.size > 5 * 1024 * 1024) {
                if (errorLabel) {
                    errorLabel.textContent = "File exceeds the 5 MB maximum upload limit.";
                }
                fileInput.value = "";
                if (previewContainer) previewContainer.classList.remove("visible");
                return;
            }

            const reader = new FileReader();
            reader.onload = (ev) => {
                if (previewImg && previewContainer) {
                    previewImg.src = ev.target.result;
                    if (previewLabel) {
                        const kb = (file.size / 1024).toFixed(1);
                        previewLabel.textContent = `${file.name} (${kb} KB)`;
                    }
                    previewContainer.classList.add("visible");
                }
            };
            reader.readAsDataURL(file);
        }
    });

    // 4. Form Submit Loading State
    const forms = document.querySelectorAll("form[data-loading-text]");
    forms.forEach((form) => {
        form.addEventListener("submit", () => {
            const btn = form.querySelector("button[type='submit']");
            if (btn && !btn.disabled) {
                btn.dataset.originalText = btn.innerHTML;
                btn.innerHTML = `<span>${form.dataset.loadingText}</span>`;
                btn.disabled = true;
            }
        });
    });

    // 5. Demo Account Quick-Fill Buttons on Login Page (Helpful during DBMS Viva)
    const demoButtons = document.querySelectorAll("[data-fill-identifier]");
    demoButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
            const idInput = document.getElementById("identifier");
            const pwInput = document.getElementById("password");
            if (idInput && pwInput) {
                idInput.value = btn.dataset.fillIdentifier;
                pwInput.value = btn.dataset.fillPassword;
                idInput.focus();
            }
        });
    });

    // 6. Sync aria-invalid with native CSS :user-invalid state after interaction
    const syncAria = (el) => {
        if (el && typeof el.matches === "function" && el.classList.contains("form-control")) {
            el.setAttribute("aria-invalid", el.matches(":user-invalid") ? "true" : "false");
        }
    };
    document.addEventListener("blur", (e) => syncAria(e.target), true);
    document.addEventListener("input", (e) => {
        if (e.target && e.target.hasAttribute && e.target.hasAttribute("aria-invalid")) {
            syncAria(e.target);
        }
    });
});
