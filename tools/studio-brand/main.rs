//! Dependency-free brand asset compiler. Run as WASI to avoid native build-tool installs.
use std::{env, fs, io, path::Path};

const POINTS: [(f64, f64); 12] = [(48.,14.),(23.,14.),(14.,23.),(14.,29.),(34.,41.),(17.,41.),(17.,50.),(41.,50.),(50.,41.),(50.,35.),(30.,23.),(48.,23.)];
const SVG: &str = r##"<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><path id="mark" d="M48 14H23L14 23V29L34 41H17V50H41L50 41V35L30 23H48Z"/><clipPath id="lower"><path d="M0 32h64v32H0z"/></clipPath></defs><rect x="1" y="1" width="62" height="62" rx="14" fill="#181b20" stroke="#414953"/><use href="#mark" fill="#f1f5f9"/><use href="#mark" clip-path="url(#lower)" fill="#22b8f0"/><path d="M49 7h6l3 3h-6z" fill="#f4bc61"/></svg>"##;

fn inside(x: f64, y: f64) -> bool {
    let mut hit = false;
    let mut previous = POINTS.len() - 1;
    for i in 0..POINTS.len() {
        let (ax, ay) = POINTS[i];
        let (bx, by) = POINTS[previous];
        if (ay > y) != (by > y) && x < (bx-ax)*(y-ay)/(by-ay)+ax { hit = !hit; }
        previous = i;
    }
    hit
}

fn sample(x: f64, y: f64) -> [u8; 4] {
    let dx = (x - 32.).abs() - 17.;
    let dy = (y - 32.).abs() - 17.;
    let distance = dx.max(0.).hypot(dy.max(0.)) + dx.max(dy).min(0.) - 14.;
    if distance > 0. { return [0; 4]; }
    if inside(x, y) { return if y >= 32. { [34,184,240,255] } else { [241,245,249,255] }; }
    if (7. ..10.).contains(&y) && x >= 49. + y - 7. && x <= 55. + y - 7. { return [244,188,97,255]; }
    if distance > -1. { [65,73,83,255] } else { [24,27,32,255] }
}

fn bitmap(size: usize) -> Vec<u8> {
    let mask_stride = size.div_ceil(32) * 4;
    let mut data = Vec::new();
    for value in [40u32, size as u32, (size*2) as u32] { data.extend(value.to_le_bytes()); }
    data.extend(1u16.to_le_bytes()); data.extend(32u16.to_le_bytes());
    for value in [0u32, (size*size*4) as u32, 0, 0, 0, 0] { data.extend(value.to_le_bytes()); }
    let mut mask = vec![0u8; mask_stride * size];
    for row in 0..size {
        for column in 0..size {
            let mut sum = [0u32; 4];
            for sy in 0..4 { for sx in 0..4 {
                let pixel = sample((column as f64+(sx as f64+0.5)/4.)*64./size as f64,
                    ((size-1-row) as f64+(sy as f64+0.5)/4.)*64./size as f64);
                for c in 0..3 { sum[c] += pixel[c] as u32 * pixel[3] as u32; }
                sum[3] += pixel[3] as u32;
            }}
            let alpha = (sum[3]/16) as u8;
            let rgb = |c: usize| if sum[3] == 0 { 0 } else { (sum[c]/sum[3]) as u8 };
            data.extend([rgb(2),rgb(1),rgb(0),alpha]);
            if alpha == 0 { mask[row*mask_stride+column/8] |= 0x80 >> (column%8); }
        }
    }
    data.extend(mask);
    data
}

fn main() -> io::Result<()> {
    let output = env::args().nth(1).expect("Usage: studio-brand OUTPUT_DIRECTORY");
    let output = Path::new(&output);
    fs::create_dir_all(output)?;
    fs::write(output.join("sovereign-mark.svg"), SVG)?;
    let sizes = [16usize,24,32,48,64,128,256];
    let bitmaps: Vec<_> = sizes.iter().map(|&n| bitmap(n)).collect();
    let mut ico = vec![0u8,0,1,0,sizes.len() as u8,0];
    let mut offset = 6+16*sizes.len();
    for (&size, bitmap) in sizes.iter().zip(&bitmaps) {
        ico.extend([size as u8,size as u8,0,0]);
        ico.extend(1u16.to_le_bytes()); ico.extend(32u16.to_le_bytes());
        ico.extend((bitmap.len() as u32).to_le_bytes()); ico.extend((offset as u32).to_le_bytes());
        offset += bitmap.len();
    }
    for bitmap in bitmaps { ico.extend(bitmap); }
    fs::write(output.join("sovereign-studio.ico"), ico)?;
    println!("Generated SVG and seven-resolution ICO in {}", output.display());
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn silhouette_has_open_negative_space() { assert!(inside(24.,18.)); assert!(!inside(10.,32.)); }
    #[test] fn icon_geometry_is_correct() {
        for size in [16usize,24,32,48,64,128,256] {
            assert_eq!(bitmap(size).len(),40+size*size*4+size.div_ceil(32)*4*size);
        }
    }
    #[test] fn alpha_and_colors_are_valid() {
        assert_eq!(sample(0.,0.)[3],0);
        assert_eq!(sample(24.,18.),[241,245,249,255]);
        assert_eq!(sample(24.,45.),[34,184,240,255]);
    }
}
