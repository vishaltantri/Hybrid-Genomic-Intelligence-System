"""VCF 4.2+ parser and normalizer for GENOMIND-INDIA / Genomera (Phase 3B).

Parses single and multi-sample VCF lines, decomposes multi-allelic sites,
extracts FORMAT/sample fields (GT, DP, AD, GQ), normalizes INDELs and chromosome IDs.
"""
from __future__ import annotations

import gzip
import io
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union


@dataclass
class VariantRecord:
    chrom: str
    pos: int
    id: str
    ref: str
    alt: str
    qual: Optional[float]
    filter: str
    info: Dict[str, Any]
    samples: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Normalized coordinates
    norm_chrom: str = ""
    norm_pos: int = 0
    norm_ref: str = ""
    norm_alt: str = ""
    
    # Derivations
    allele_index: int = 0  # 0-indexed for multi-allelic breakdown
    genotype: str = ""     # e.g. "0/1", "1/1", "0/0"
    zygosity: str = "Unknown"  # "Heterozygous", "Homozygous", "Hemizygous", "Reference"
    depth: Optional[int] = None
    allele_depth: Optional[List[int]] = None
    genotype_quality: Optional[float] = None
    variant_id: str = ""   # e.g. "chr13:31998246:C>G"

    def __post_init__(self):
        if not self.norm_chrom:
            self.norm_chrom = normalize_chrom(self.chrom)
        if not self.norm_pos:
            self.norm_pos = self.pos
        if not self.norm_ref:
            self.norm_ref = self.ref.upper()
        if not self.norm_alt:
            self.norm_alt = self.alt.upper()
        if not self.variant_id:
            self.variant_id = f"{self.norm_chrom}:{self.norm_pos}:{self.norm_ref}>{self.norm_alt}"


def normalize_chrom(chrom: str) -> str:
    """Standardize chromosome naming to 'chr1'..'chr22', 'chrX', 'chrY', 'chrM'."""
    c = str(chrom).strip()
    if c.startswith("chr") or c.startswith("CHR"):
        c = c[3:]
    c_upper = c.upper()
    if c_upper == "MT":
        c_upper = "M"
    return f"chr{c_upper}"


def left_align_and_trim(pos: int, ref: str, alt: str) -> Tuple[int, str, str]:
    """Trim shared suffixes and prefixes to normalize indels."""
    ref = ref.upper()
    alt = alt.upper()
    
    # Trim common suffix
    while len(ref) > 1 and len(alt) > 1 and ref[-1] == alt[-1]:
        ref = ref[:-1]
        alt = alt[:-1]
        
    # Trim common prefix
    while len(ref) > 1 and len(alt) > 1 and ref[0] == alt[0]:
        ref = ref[1:]
        alt = alt[1:]
        pos += 1
        
    return pos, ref, alt


def parse_vcf_header(lines: List[str]) -> Tuple[List[str], Dict[str, Any], List[str]]:
    """Extract metadata headers, format definitions, and sample names."""
    metadata = {}
    samples = []
    header_lines = []
    
    for line in lines:
        if line.startswith("##"):
            header_lines.append(line)
            if "=" in line:
                m = re.match(r"^##([^=]+)=(.*)$", line)
                if m:
                    key, val = m.group(1), m.group(2)
                    if key not in metadata:
                        metadata[key] = []
                    metadata[key].append(val)
        elif line.startswith("#CHROM"):
            parts = line.strip().split("\t")
            if len(parts) >= 10:
                samples = parts[9:]
            break
            
    return header_lines, metadata, samples


def parse_info_field(info_str: str) -> Dict[str, Any]:
    """Parse key=value pairs or boolean flags from INFO column."""
    if not info_str or info_str == ".":
        return {}
    res = {}
    tokens = info_str.split(";")
    for tok in tokens:
        if "=" in tok:
            k, v = tok.split("=", 1)
            # Try float/int conversion
            if re.match(r"^-?\d+$", v):
                res[k] = int(v)
            elif re.match(r"^-?\d+\.\d+$", v):
                res[k] = float(v)
            else:
                res[k] = v
        else:
            res[tok] = True
    return res


def parse_format_and_samples(format_str: str, sample_strs: List[str], sample_names: List[str]) -> Dict[str, Dict[str, Any]]:
    """Parse FORMAT keys (GT, DP, AD, GQ, etc.) for each sample."""
    if not format_str or format_str == "." or not sample_strs:
        return {}
        
    keys = format_str.split(":")
    sample_data = {}
    
    for i, s_str in enumerate(sample_strs):
        s_name = sample_names[i] if i < len(sample_names) else f"SAMPLE_{i+1}"
        s_vals = s_str.split(":")
        entry = {}
        for k, v in zip(keys, s_vals):
            if v == ".":
                entry[k] = None
            elif k in ("DP", "GQ") and re.match(r"^\d+$", v):
                entry[k] = int(v)
            elif k == "AD" and "," in v:
                try:
                    entry[k] = [int(x) for x in v.split(",") if x.isdigit()]
                except Exception:
                    entry[k] = v
            else:
                entry[k] = v
        sample_data[s_name] = entry
        
    return sample_data


def determine_zygosity(gt: Optional[str]) -> str:
    """Determine zygosity from genotype string (e.g. 0/1, 1/1, 1|1)."""
    if not gt or gt in (".", "./.", ".|."):
        return "Unknown"
    
    alleles = re.split(r"[/|]", gt)
    if len(alleles) == 1:
        return "Hemizygous" if alleles[0] not in ("0", ".") else "Reference"
    elif len(alleles) == 2:
        a1, a2 = alleles[0], alleles[1]
        if a1 == "0" and a2 == "0":
            return "Reference"
        elif a1 == a2 and a1 not in ("0", "."):
            return "Homozygous"
        elif a1 != a2 and (a1 not in ("0", ".") or a2 not in ("0", ".")):
            return "Heterozygous"
    return "Complex"


def parse_vcf_content(content: Union[str, bytes], default_sample_name: str = "PROBAND") -> Tuple[List[VariantRecord], Dict[str, Any]]:
    """Parse VCF text or gzipped bytes into normalized VariantRecord objects."""
    if isinstance(content, bytes):
        # Detect gzip magic number
        if content[:2] == b"\x1f\x8b":
            decompressed = gzip.decompress(content).decode("utf-8", errors="replace")
        else:
            decompressed = content.decode("utf-8", errors="replace")
        lines = decompressed.splitlines()
    else:
        lines = content.splitlines()
        
    header_lines, metadata, sample_names = parse_vcf_header(lines)
    if not sample_names:
        sample_names = [default_sample_name]
        
    records: List[VariantRecord] = []
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
            
        parts = line.split("\t")
        if len(parts) < 8:
            continue
            
        chrom = parts[0]
        try:
            pos = int(parts[1])
        except ValueError:
            continue
            
        var_id = parts[2]
        ref = parts[3]
        alts = parts[4].split(",")
        qual = float(parts[5]) if parts[5] != "." and re.match(r"^-?\d+(\.\d+)?$", parts[5]) else None
        filt = parts[6]
        info = parse_info_field(parts[7])
        
        format_str = parts[8] if len(parts) > 8 else ""
        sample_strs = parts[9:] if len(parts) > 9 else []
        samples_parsed = parse_format_and_samples(format_str, sample_strs, sample_names)
        
        # Multi-allelic decomposition: produce a VariantRecord for each ALT allele
        for alt_idx, alt in enumerate(alts):
            alt = alt.strip()
            if not alt or alt == "*":
                continue  # skip missing/deleted overlapping allele placeholders
                
            norm_pos, norm_ref, norm_alt = left_align_and_trim(pos, ref, alt)
            norm_c = normalize_chrom(chrom)
            
            # Primary sample inspection (proband or first sample)
            primary_sample_data = samples_parsed.get(sample_names[0], {}) if sample_names else {}
            gt = primary_sample_data.get("GT")
            dp = primary_sample_data.get("DP") or (info.get("DP") if isinstance(info.get("DP"), int) else None)
            ad = primary_sample_data.get("AD")
            gq = primary_sample_data.get("GQ")
            zyg = determine_zygosity(gt)
            
            rec = VariantRecord(
                chrom=chrom,
                pos=pos,
                id=var_id,
                ref=ref,
                alt=alt,
                qual=qual,
                filter=filt,
                info=info,
                samples=samples_parsed,
                norm_chrom=norm_c,
                norm_pos=norm_pos,
                norm_ref=norm_ref,
                norm_alt=norm_alt,
                allele_index=alt_idx,
                genotype=gt or "Unknown",
                zygosity=zyg,
                depth=dp,
                allele_depth=ad if isinstance(ad, list) else None,
                genotype_quality=gq,
                variant_id=f"{norm_c}:{norm_pos}:{norm_ref}>{norm_alt}",
            )
            records.append(rec)
            
    summary = {
        "total_variants": len(records),
        "samples": sample_names,
        "is_multisample": len(sample_names) > 1,
        "header_lines_count": len(header_lines),
    }
    return records, summary
