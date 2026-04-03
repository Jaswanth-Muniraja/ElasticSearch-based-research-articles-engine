"""
config.py — Environment configuration and constants for the Research Portal backend.
Loads settings from .env and exposes typed constants used across all modules.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the backend directory
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_env_path)

# ── Elasticsearch ────────────────────────────────────────────────────────────
ELASTICSEARCH_URL: str = os.getenv("ELASTICSEARCH_URL", "https://localhost:9200")
ELASTICSEARCH_INDEX: str = os.getenv("ELASTICSEARCH_INDEX", "research_papers")
ELASTICSEARCH_USERNAME: str = os.getenv("ELASTICSEARCH_USERNAME", "qwerty")
ELASTICSEARCH_PASSWORD: str = os.getenv("ELASTICSEARCH_PASSWORD", "abcdefg")

# ── Papers folder (resolved relative to this file's parent) ──────────────────
_raw_papers = os.getenv("PAPERS_FOLDER", "../papers")
PAPERS_FOLDER: Path = (Path(__file__).resolve().parent / _raw_papers).resolve()

# ── Sync interval ────────────────────────────────────────────────────────────
SYNC_INTERVAL_MINUTES: int = int(os.getenv("SYNC_INTERVAL_MINUTES", "5"))

# ── CORS ─────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

# ── Server ───────────────────────────────────────────────────────────────────
API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("API_PORT", "8000"))

# ── Admin credentials ────────────────────────────────────────────────────────
ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "qwerty@xyz.com")
ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "qwerty@1234")
JWT_SECRET: str = os.getenv("JWT_SECRET", "qwertyuiopasdfghjklzxcvbnm")

# ── Domain keyword dictionaries ──────────────────────────────────────────────
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "AI/ML": [
        "artificial intelligence", "machine learning", "deep learning",
        "neural network", "reinforcement learning", "supervised learning",
        "unsupervised learning", "gradient descent", "backpropagation",
        "convolutional neural network", "recurrent neural network",
        "generative adversarial network", "transfer learning", "ensemble",
        "random forest", "decision tree", "support vector machine",
        "logistic regression", "k-nearest neighbor", "clustering",
        "classification", "regression", "feature engineering",
        "hyperparameter", "overfitting", "underfitting",
    ],
    "NLP": [
        "natural language processing", "text mining", "sentiment analysis",
        "named entity recognition", "part-of-speech", "tokenization",
        "word embedding", "word2vec", "glove", "bert", "gpt",
        "transformer", "attention mechanism", "language model",
        "text classification", "machine translation", "question answering",
        "text generation", "large language model", "llm", "chatbot",
        "speech recognition", "text summarization",
    ],
    "Computer Vision": [
        "computer vision", "image recognition", "object detection",
        "image segmentation", "face recognition", "optical character recognition",
        "image classification", "yolo", "resnet", "vgg", "inception",
        "gan", "image generation", "video analysis", "pose estimation",
        "depth estimation", "point cloud", "lidar",
    ],
    "Cybersecurity": [
        "cybersecurity", "encryption", "cryptography", "firewall",
        "intrusion detection", "malware", "phishing", "vulnerability",
        "penetration testing", "authentication", "authorization",
        "access control", "threat", "ransomware", "ddos",
        "network security", "information security", "privacy",
        "zero trust", "blockchain security",
    ],
    "IoT": [
        "internet of things", "iot", "sensor", "embedded system",
        "smart home", "smart city", "wearable", "edge computing",
        "fog computing", "mqtt", "zigbee", "bluetooth low energy",
        "raspberry pi", "arduino", "microcontroller",
    ],
    "Cloud Computing": [
        "cloud computing", "aws", "azure", "google cloud",
        "kubernetes", "docker", "microservices", "serverless",
        "saas", "paas", "iaas", "virtualization", "container",
        "load balancing", "auto scaling", "cloud native",
    ],
    "Blockchain": [
        "blockchain", "cryptocurrency", "bitcoin", "ethereum",
        "smart contract", "distributed ledger", "consensus mechanism",
        "proof of work", "proof of stake", "decentralized",
        "nft", "token", "mining", "hash function",
    ],
    "Data Science": [
        "data science", "big data", "data mining", "data analytics",
        "data visualization", "pandas", "numpy", "matplotlib",
        "statistical analysis", "hypothesis testing", "a/b testing",
        "etl", "data pipeline", "data warehouse", "data lake",
        "apache spark", "hadoop", "sql", "nosql",
    ],
    "Quantum Computing": [
        "quantum computing", "qubit", "quantum entanglement",
        "quantum supremacy", "quantum algorithm", "quantum gate",
        "quantum error correction", "shor algorithm", "grover algorithm",
        "quantum machine learning",
    ],
    "Databases": [
        "database", "relational database", "sql", "nosql", "mongodb",
        "postgresql", "mysql", "redis", "elasticsearch", "cassandra",
        "graph database", "neo4j", "query optimization", "indexing",
        "sharding", "replication", "acid", "transaction",
    ],
    # ── ECE Domains ──────────────────────────────────────────────────────
    "VLSI": [
        "vlsi", "very large scale integration", "cmos", "mosfet", "finfet",
        "asic", "fpga", "verilog", "vhdl", "soc", "system on chip",
        "digital design", "analog design", "mixed signal", "ic design",
        "semiconductor", "fabrication", "lithography", "rtl", "synthesis",
        "place and route", "physical design", "timing analysis",
        "low power design", "clock gating", "dft", "design for testability",
    ],
    "Communication Systems": [
        "wireless communication", "5g", "6g", "lte", "ofdm", "mimo",
        "antenna", "rf", "radio frequency", "modulation", "demodulation",
        "signal propagation", "channel estimation", "beamforming",
        "spectrum", "cognitive radio", "millimeter wave", "free space optics",
        "satellite communication", "optical communication", "fiber optic",
        "software defined radio", "mobile communication", "cellular network",
        "spread spectrum", "frequency hopping", "channel coding",
    ],
    "Signal Processing": [
        "signal processing", "digital signal processing", "dsp",
        "fourier transform", "fft", "wavelet", "filter design",
        "adaptive filter", "kalman filter", "noise reduction",
        "audio processing", "speech processing", "image processing",
        "sampling", "quantization", "spectral analysis", "convolution",
        "autocorrelation", "power spectral density", "stochastic signal",
    ],
    "Embedded Systems": [
        "embedded system", "microprocessor", "microcontroller", "arm",
        "rtos", "real time operating system", "firmware", "bootloader",
        "device driver", "interrupt", "timer", "adc", "dac", "uart",
        "spi", "i2c", "can bus", "gpio", "watchdog", "dma",
        "embedded linux", "bare metal", "system architecture",
    ],
    "Power Electronics": [
        "power electronics", "inverter", "converter", "rectifier",
        "pwm", "pulse width modulation", "mosfet driver", "igbt",
        "buck converter", "boost converter", "flyback", "half bridge",
        "full bridge", "power supply", "voltage regulator", "dc-dc",
        "ac-dc", "power factor correction", "harmonic analysis",
        "solar inverter", "motor drive", "variable frequency drive",
    ],
    # ── Mechanical Engineering Domains ────────────────────────────────────
    "Automobile Engineering": [
        "automobile", "automotive", "vehicle dynamics", "engine",
        "combustion", "internal combustion", "transmission", "braking system",
        "suspension", "chassis", "aerodynamics", "electric vehicle",
        "hybrid vehicle", "battery management", "fuel cell", "turbocharger",
        "exhaust system", "emission control", "autonomous vehicle",
        "adas", "advanced driver assistance", "vehicle safety",
    ],
    "Robotics": [
        "robotics", "robot", "manipulator", "end effector", "kinematics",
        "dynamics", "path planning", "motion planning", "slam",
        "simultaneous localization and mapping", "ros", "robot operating system",
        "actuator", "servo motor", "stepper motor", "pid control",
        "inverse kinematics", "forward kinematics", "humanoid",
        "swarm robotics", "mobile robot", "industrial robot",
        "collaborative robot", "cobot", "gripper", "haptics",
    ],
    "Structural Engineering": [
        "structural analysis", "finite element", "finite element method",
        "fem", "fea", "stress analysis", "strain", "deformation",
        "buckling", "fatigue", "fracture mechanics", "composite material",
        "concrete structure", "steel structure", "beam", "truss",
        "frame", "shell structure", "vibration analysis", "modal analysis",
        "earthquake engineering", "seismic", "structural dynamics",
    ],
    "Thermal Engineering": [
        "heat transfer", "thermodynamics", "conduction", "convection",
        "radiation", "heat exchanger", "refrigeration", "hvac",
        "air conditioning", "compressor", "turbine", "boiler",
        "steam", "entropy", "enthalpy", "thermal conductivity",
        "computational fluid dynamics", "cfd", "navier stokes",
        "boundary layer", "turbulence", "fluid mechanics", "fluid flow",
        "nusselt number", "reynolds number", "prandtl number",
    ],
    "Manufacturing Engineering": [
        "manufacturing", "cnc", "computer numerical control", "machining",
        "casting", "forging", "welding", "additive manufacturing",
        "3d printing", "injection molding", "sheet metal", "turning",
        "milling", "drilling", "grinding", "surface finish",
        "tolerance", "metrology", "quality control", "lean manufacturing",
        "six sigma", "supply chain", "cad", "cam", "cae",
        "rapid prototyping", "industry 4.0", "smart manufacturing",
    ],
    # ── Civil Engineering ─────────────────────────────────────────────────
    "Civil Engineering": [
        "civil engineering", "construction", "geotechnical", "foundation",
        "soil mechanics", "concrete", "reinforced concrete", "prestressed",
        "highway", "pavement", "transportation engineering", "traffic",
        "water resources", "hydrology", "hydraulics", "dam",
        "irrigation", "drainage", "surveying", "gis",
        "geographic information system", "remote sensing", "urban planning",
        "building information modeling", "bim", "green building",
        "sustainable construction", "bridge engineering", "tunnel",
    ],
    # ── Electrical Engineering ────────────────────────────────────────────
    "Electrical Engineering": [
        "electrical engineering", "power system", "electric grid",
        "transformer", "generator", "electric motor", "induction motor",
        "synchronous machine", "power distribution", "smart grid",
        "renewable energy", "solar energy", "wind energy", "photovoltaic",
        "energy storage", "battery", "supercapacitor", "protection system",
        "relay", "circuit breaker", "load flow", "power quality",
        "energy management", "microgrid", "electric power",
        "high voltage", "insulation", "switchgear",
    ],
    # ── Biotechnology ─────────────────────────────────────────────────────
    "Biotechnology": [
        "biotechnology", "genetic engineering", "gene editing", "crispr",
        "pcr", "polymerase chain reaction", "dna sequencing", "genomics",
        "proteomics", "metabolomics", "recombinant dna", "cloning",
        "fermentation", "bioprocess", "bioreactor", "enzyme",
        "protein engineering", "antibody", "immunology", "vaccine",
        "cell culture", "stem cell", "tissue engineering",
        "biomaterial", "biosensor", "biomarker", "gene therapy",
        "transgenic", "molecular biology", "microbiology",
    ],
    # ── Chemistry ─────────────────────────────────────────────────────────
    "Chemistry": [
        "organic chemistry", "inorganic chemistry", "physical chemistry",
        "analytical chemistry", "chemical synthesis", "catalysis",
        "spectroscopy", "chromatography", "mass spectrometry",
        "nmr", "nuclear magnetic resonance", "infrared spectroscopy",
        "electrochemistry", "polymer chemistry", "coordination chemistry",
        "thermochemistry", "photochemistry", "green chemistry",
        "supramolecular chemistry", "surface chemistry", "colloid",
        "reaction kinetics", "chemical equilibrium", "molecular orbital",
    ],
    # ── Physics ───────────────────────────────────────────────────────────
    "Physics": [
        "quantum mechanics", "condensed matter", "solid state physics",
        "semiconductor physics", "superconductor", "magnetism",
        "optics", "photonics", "laser", "plasma physics",
        "nuclear physics", "particle physics", "astrophysics",
        "cosmology", "general relativity", "special relativity",
        "statistical mechanics", "electrodynamics", "electromagnetic",
        "wave mechanics", "thin film", "crystallography",
        "x-ray diffraction", "raman spectroscopy", "quantum field theory",
    ],
    # ── Mathematics & Statistics ──────────────────────────────────────────
    "Mathematics": [
        "linear algebra", "differential equations", "calculus",
        "numerical methods", "optimization", "graph theory",
        "combinatorics", "number theory", "probability", "statistics",
        "stochastic process", "markov chain", "monte carlo",
        "mathematical modeling", "dynamical system", "chaos theory",
        "topology", "abstract algebra", "functional analysis",
        "partial differential equations", "integral equations",
        "approximation theory", "computational mathematics",
    ],
    # ── Bioinformatics ────────────────────────────────────────────────────
    "Bioinformatics": [
        "bioinformatics", "sequence alignment", "blast", "phylogenetics",
        "gene expression", "microarray", "rna sequencing", "rna-seq",
        "variant calling", "genome assembly", "metagenomics",
        "protein structure prediction", "homology modeling",
        "molecular docking", "drug discovery", "systems biology",
        "pathway analysis", "network biology", "epigenetics",
        "single cell", "transcriptomics",
    ],
    # ── Environmental Science ─────────────────────────────────────────────
    "Environmental Science": [
        "environmental science", "pollution", "air quality",
        "water treatment", "wastewater", "solid waste", "recycling",
        "climate change", "global warming", "carbon footprint",
        "greenhouse gas", "biodiversity", "ecology", "ecosystem",
        "sustainability", "environmental impact assessment",
        "life cycle assessment", "soil contamination", "phytoremediation",
        "renewable resources", "conservation", "deforestation",
    ],
    # ── Nanotechnology ────────────────────────────────────────────────────
    "Nanotechnology": [
        "nanotechnology", "nanoparticle", "nanomaterial", "nanocomposite",
        "carbon nanotube", "graphene", "quantum dot", "nanofiber",
        "nanowire", "nanostructure", "self assembly",
        "atomic force microscopy", "scanning electron microscopy",
        "transmission electron microscopy", "nanofabrication",
        "nanolithography", "nanoelectronics", "nanophotonics",
        "nanomedicine", "drug delivery", "nano coating",
    ],
    # ── Aerospace Engineering ─────────────────────────────────────────────
    "Aerospace Engineering": [
        "aerospace", "aeronautics", "aircraft", "airfoil",
        "computational fluid dynamics", "wind tunnel", "propulsion",
        "jet engine", "rocket", "spacecraft", "satellite",
        "orbital mechanics", "flight dynamics", "avionics",
        "uav", "unmanned aerial vehicle", "drone", "helicopter",
        "supersonic", "hypersonic", "composite materials",
        "aeroelasticity", "flight control", "navigation",
    ],
    # ── Networking & Telecom ──────────────────────────────────────────────
    "Networking": [
        "computer network", "tcp/ip", "routing", "switching",
        "network protocol", "lan", "wan", "vpn", "sdn",
        "software defined networking", "network function virtualization",
        "network security", "packet", "bandwidth", "latency",
        "throughput", "quality of service", "qos", "network topology",
        "ethernet", "wifi", "wimax", "optical networking",
        "mpls", "bgp", "ospf", "dns", "dhcp", "http",
    ],
}

# ── Elasticsearch index mapping ──────────────────────────────────────────────
INDEX_MAPPING = {
    "settings": {
        "analysis": {
            "filter": {
                "english_stop": {
                    "type": "stop",
                    "stopwords": "_english_",
                },
                "synonym_filter": {
                    "type": "synonym",
                    "synonyms": [
                        "ai, artificial intelligence",
                        "ml, machine learning",
                        "nlp, natural language processing",
                        "dl, deep learning",
                        "nn, neural network",
                        "cv, computer vision",
                        "rl, reinforcement learning",
                        "iot, internet of things",
                        "llm, large language model",
                        "dsa, data structures and algorithms",
                        "os, operating system",
                        "db, database",
                        "cn, computer network",
                        "se, software engineering",
                        "cd, computer design",
                        "coa, computer organization and architecture",
                        "toc, theory of computation",
                        "dbms, database management system",
                        "sd, software design",
                        "se, software engineering",
                    ],
                },
            },
            "analyzer": {
                "english_synonyms": {
                    "tokenizer": "standard",
                    "filter": [
                        "lowercase",
                        "english_stop",
                        "synonym_filter",
                        "porter_stem",
                    ],
                },
            },
        },
    },
    "mappings": {
        "properties": {
            "title":           {"type": "text", "analyzer": "english"},
            "authors":         {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "emails":          {"type": "keyword"},
            "abstract":        {"type": "text", "analyzer": "english"},
            "keywords":        {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "domain_keywords": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "ner_entities":    {"type": "text"},
            "full_text":       {"type": "text", "analyzer": "english"},
            "file_name":       {"type": "keyword"},
            "file_path":       {"type": "keyword"},
            "file_size_bytes": {"type": "long"},
            "file_size_human": {"type": "keyword"},
            "page_count":      {"type": "integer"},
            "sha256_hash":     {"type": "keyword"},
            "date_indexed":    {"type": "date"},
            "last_modified":   {"type": "date"},
            "edited":          {"type": "boolean"},
            "last_edited_by":  {"type": "keyword"},
            "last_edited_at":  {"type": "date"},
        },
    },
}
