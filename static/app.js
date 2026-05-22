const form = document.getElementById('mosaicForm');
const statusBox = document.getElementById('status');
const resultBox = document.getElementById('result');
const submitBtn = form.querySelector('.primary-btn');
const downloadLink = document.getElementById('downloadLink');

const tilesInput = document.getElementById('tilesInput');
const targetInput = document.getElementById('targetInput');
const dynamicSuggestionGrid = document.getElementById('dynamicSuggestionGrid');
const staticSuggestionGrid = document.getElementById('staticSuggestionGrid');
const suggestionHint = document.getElementById('suggestionHint');
const photoScanBox = document.getElementById('photoScanBox');
const scanFill = document.getElementById('scanFill');
const scanCount = document.getElementById('scanCount');
const scanText = document.getElementById('scanText');

const generateProgressBox = document.getElementById('generateProgressBox');
const generateFill = document.getElementById('generateFill');
const generatePercent = document.getElementById('generatePercent');
const generateTitle = document.getElementById('generateTitle');
const generateText = document.getElementById('generateText');

let currentJobId = null;
let currentDownloadName = null;
let suggestedPortraits = [];
let selectedSuggestedFile = null;
let processingTimer = null;

function bindPrettyFileInput(inputId, labelSelector, nameId, emptyText) {
  const input = document.getElementById(inputId);
  const label = document.querySelector(labelSelector);
  const nameBox = document.getElementById(nameId);
  if (!input || !label || !nameBox) return;

  input.addEventListener('change', () => {
    const files = Array.from(input.files || []);
    if (!files.length) {
      nameBox.textContent = emptyText;
      label.classList.remove('has-file');
      return;
    }

    label.classList.add('has-file');
    nameBox.textContent = files.length === 1 ? files[0].name : `${files.length} photos selected`;
  });
}

bindPrettyFileInput('tilesInput', 'label[for="tilesInput"]', 'tilesFileName', 'No files selected');
bindPrettyFileInput('targetInput', 'label[for="targetInput"]', 'targetFileName', 'Optional — auto-pick if empty');

function showStatus(message, isError = false) {
  statusBox.textContent = message;
  statusBox.classList.remove('hidden');
  statusBox.classList.toggle('error', isError);
}

function hideStatus() {
  statusBox.classList.add('hidden');
}

function setScanProgress(done, total, text) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  photoScanBox.classList.remove('hidden');
  scanFill.style.width = `${pct}%`;
  scanCount.textContent = `${done} / ${total}`;
  scanText.textContent = text || 'Finding the best portrait options from your uploaded photos.';
}

function setGenerateProgress(percent, title, text) {
  const safe = Math.max(0, Math.min(100, Math.round(percent)));
  generateProgressBox.classList.remove('hidden');
  generateFill.style.width = `${safe}%`;
  generatePercent.textContent = `${safe}%`;
  generateTitle.textContent = title;
  generateText.textContent = text;
}

function hideGenerateProgress() {
  clearInterval(processingTimer);
  processingTimer = null;
  generateProgressBox.classList.add('hidden');
}

function readImageFile(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => resolve({ img, url });
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error(`Could not read ${file.name}`));
    };
    img.src = url;
  });
}

function scorePortraitCandidate(image) {
  const canvas = document.createElement('canvas');
  const size = 96;
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(image, 0, 0, size, size);
  const data = ctx.getImageData(0, 0, size, size).data;

  let brightness = 0;
  let contrast = 0;
  let centerBrightness = 0;
  let centerContrast = 0;
  let centerPixels = 0;
  let prevLum = null;
  let edgeScore = 0;

  const lums = [];
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const i = (y * size + x) * 4;
      const lum = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
      lums.push(lum);
      brightness += lum;
      if (prevLum !== null) edgeScore += Math.abs(lum - prevLum);
      prevLum = lum;

      if (x > size * 0.28 && x < size * 0.72 && y > size * 0.20 && y < size * 0.78) {
        centerBrightness += lum;
        centerPixels += 1;
      }
    }
  }

  const mean = brightness / lums.length;
  for (const lum of lums) contrast += Math.abs(lum - mean);
  const avgContrast = contrast / lums.length;
  const avgCenterBrightness = centerBrightness / Math.max(centerPixels, 1);

  for (let y = 22; y < 74; y += 2) {
    for (let x = 28; x < 68; x += 2) {
      const i = (y * size + x) * 4;
      const lum = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
      centerContrast += Math.abs(lum - avgCenterBrightness);
    }
  }

  const aspect = image.width / image.height;
  const portraitShape = aspect < 0.95 ? 1 : aspect <= 1.25 ? 0.72 : 0.36;
  const usableLight = mean > 70 && mean < 210 ? 1 : 0.55;
  const centerLight = avgCenterBrightness > 75 && avgCenterBrightness < 220 ? 1 : 0.65;
  const sharpness = Math.min(edgeScore / 75000, 1);
  const detail = Math.min((avgContrast + centerContrast / 600) / 70, 1);
  const resolution = Math.min((image.width * image.height) / (1200 * 1200), 1);

  return (portraitShape * 30) + (usableLight * 18) + (centerLight * 14) + (sharpness * 16) + (detail * 14) + (resolution * 8);
}

async function buildPortraitSuggestions() {
  const files = Array.from(tilesInput.files || []);
  suggestedPortraits = [];
  selectedSuggestedFile = null;
  dynamicSuggestionGrid.innerHTML = '';
  dynamicSuggestionGrid.classList.add('hidden');
  staticSuggestionGrid.classList.remove('hidden');
  suggestionHint.classList.add('hidden');

  if (!files.length) {
    photoScanBox.classList.add('hidden');
    return;
  }

  setScanProgress(0, files.length, 'Checking your uploaded photos for the best portrait options...');

  const scored = [];
  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    try {
      const { img, url } = await readImageFile(file);
      const score = scorePortraitCandidate(img);
      scored.push({ file, url, score, width: img.width, height: img.height });
    } catch (e) {
      console.warn(e.message);
    }
    setScanProgress(i + 1, files.length, `Checked ${i + 1} of ${files.length} photos.`);
    await new Promise(requestAnimationFrame);
  }

  scored.sort((a, b) => b.score - a.score);
  suggestedPortraits = scored.slice(0, 3);

  if (!suggestedPortraits.length) {
    scanText.textContent = 'No usable image preview found. You can still upload your own main portrait.';
    return;
  }

  dynamicSuggestionGrid.innerHTML = suggestedPortraits.map((item, index) => `
    <button class="suggestion-card user-suggestion ${index === 0 ? 'selected' : ''}" type="button" data-index="${index}">
      <img src="${item.url}" alt="Suggested portrait ${index + 1}">
      <b>Suggested Portrait ${index + 1}</b>
      <small>${item.width} × ${item.height} • Score ${Math.round(item.score)}</small>
    </button>
  `).join('');

  selectedSuggestedFile = suggestedPortraits[0].file;
  dynamicSuggestionGrid.classList.remove('hidden');
  staticSuggestionGrid.classList.add('hidden');
  suggestionHint.classList.remove('hidden');
  scanText.textContent = `Best 3 suggestions ready from your ${files.length} uploaded photos. You can select one or upload your own.`;

  dynamicSuggestionGrid.querySelectorAll('.user-suggestion').forEach(btn => {
    btn.addEventListener('click', () => {
      dynamicSuggestionGrid.querySelectorAll('.user-suggestion').forEach(x => x.classList.remove('selected'));
      btn.classList.add('selected');
      selectedSuggestedFile = suggestedPortraits[Number(btn.dataset.index)].file;
      document.getElementById('targetFileName').textContent = `Using suggested portrait ${Number(btn.dataset.index) + 1}`;
      document.querySelector('label[for="targetInput"]').classList.remove('has-file');
    });
  });

  document.getElementById('targetFileName').textContent = 'Using suggested portrait 1, or upload your own below';
}

tilesInput.addEventListener('change', buildPortraitSuggestions);

targetInput.addEventListener('change', () => {
  if (targetInput.files && targetInput.files.length) {
    selectedSuggestedFile = null;
    dynamicSuggestionGrid.querySelectorAll('.user-suggestion').forEach(x => x.classList.remove('selected'));
  } else if (suggestedPortraits.length) {
    selectedSuggestedFile = suggestedPortraits[0].file;
    const first = dynamicSuggestionGrid.querySelector('.user-suggestion');
    if (first) first.classList.add('selected');
  }
});

function submitWithProgress(data) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/generate');

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        const uploadPct = Math.round((event.loaded / event.total) * 55);
        setGenerateProgress(uploadPct, 'Uploading photos', `Uploaded ${uploadPct > 0 ? Math.round((event.loaded / event.total) * 100) : 0}% of selected photos.`);
      } else {
        setGenerateProgress(35, 'Uploading photos', 'Uploading selected photos...');
      }
    };

    xhr.onloadstart = () => setGenerateProgress(5, 'Starting', 'Preparing your photos...');

    xhr.onreadystatechange = () => {
      if (xhr.readyState === 2 || xhr.readyState === 3) {
        let progress = 58;
        clearInterval(processingTimer);
        processingTimer = setInterval(() => {
          progress = Math.min(progress + 2, 94);
          setGenerateProgress(progress, 'Creating mosaic', 'Matching colors, blending tiles, and rendering artwork...');
        }, 900);
      }
    };

    xhr.onload = () => {
      clearInterval(processingTimer);
      processingTimer = null;
      try {
        const json = JSON.parse(xhr.responseText || '{}');
        if (xhr.status < 200 || xhr.status >= 300 || !json.ok) {
          reject(new Error(json.error || 'Something went wrong.'));
          return;
        }
        setGenerateProgress(100, 'Complete', 'Mosaic generated successfully.');
        resolve(json);
      } catch (e) {
        reject(new Error('Server returned an invalid response.'));
      }
    };

    xhr.onerror = () => {
      clearInterval(processingTimer);
      reject(new Error('Upload failed. Please try fewer/smaller photos.'));
    };

    xhr.send(data);
  });
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  hideStatus();
  resultBox.classList.add('hidden');

  const tiles = tilesInput.files;
  if (tiles.length > 120) {
    showStatus('For stable Render Free hosting, please upload maximum 120 tile photos in Version 1.', true);
    return;
  }

  const data = new FormData(form);
  data.set('add_footer', form.querySelector('input[name="add_footer"]').checked ? 'true' : 'false');

  if ((!targetInput.files || !targetInput.files.length) && selectedSuggestedFile) {
    data.set('target', selectedSuggestedFile, selectedSuggestedFile.name);
  }

  submitBtn.disabled = true;
  showStatus('Creating your mosaic. Progress will be shown below.');
  setGenerateProgress(0, 'Preparing', 'Preparing upload...');

  try {
    const json = await submitWithProgress(data);

    currentJobId = json.job_id;
    currentDownloadName = json.download_name;

    document.getElementById('previewImg').src = json.preview_url + '?t=' + Date.now();
    document.getElementById('cropImg').src = json.crop_url + '?t=' + Date.now();
    document.getElementById('tileCount').textContent = json.tile_count;
    document.getElementById('outputSize').textContent = `${json.width} × ${json.height}`;
    document.getElementById('targetSource').textContent = json.target_source;

    downloadLink.href = json.download_url;
    downloadLink.download = currentDownloadName || 'mosaic.jpg';

    resultBox.classList.remove('hidden');
    showStatus('Done. Your preview, detail crop, and download are ready.');
    setTimeout(hideGenerateProgress, 1200);
    resultBox.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) {
    hideGenerateProgress();
    showStatus(error.message, true);
  } finally {
    submitBtn.disabled = false;
  }
});
