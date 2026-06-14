export interface UniverseTicker {
  ticker: string;
  company_name: string;
  exchange: string;
  segment: "pharma" | "healthcare_services" | "medical_equipment" | "medical_distribution";
  is_mvp: boolean;
}

export const UNIVERSE: UniverseTicker[] = [
  { ticker: "DHG", company_name: "Cong ty Co phan Duoc Hau Giang", exchange: "HOSE", segment: "pharma", is_mvp: true },
  { ticker: "IMP", company_name: "Cong ty Co phan Duoc pham Imexpharm", exchange: "HOSE", segment: "pharma", is_mvp: true },
  { ticker: "DMC", company_name: "Cong ty Co phan Xuat nhap khau Y te Domesco", exchange: "HOSE", segment: "pharma", is_mvp: true },
  { ticker: "TRA", company_name: "Cong ty Co phan Traphaco", exchange: "HOSE", segment: "pharma", is_mvp: true },
  { ticker: "DBD", company_name: "Cong ty Co phan Duoc - Trang thiet bi Y te Binh Dinh", exchange: "HOSE", segment: "pharma", is_mvp: true },
  { ticker: "OPC", company_name: "Cong ty Co phan Duoc pham OPC", exchange: "HOSE", segment: "pharma", is_mvp: false },
  { ticker: "PME", company_name: "Cong ty Co phan Pymepharco", exchange: "HOSE", segment: "pharma", is_mvp: false },
  { ticker: "MKP", company_name: "Cong ty Co phan Hoa - Duoc pham Mekophar", exchange: "HOSE", segment: "pharma", is_mvp: false },
  { ticker: "TNH", company_name: "Cong ty Co phan Benh vien Quoc te Thai Nguyen", exchange: "HOSE", segment: "healthcare_services", is_mvp: false },
  { ticker: "JVC", company_name: "Cong ty Co phan Thiet bi Y te Viet Nhat", exchange: "HOSE", segment: "medical_equipment", is_mvp: false },
  { ticker: "DVN", company_name: "Tong Cong ty Duoc Viet Nam - CTCP", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DHT", company_name: "Cong ty Co phan Duoc pham Ha Tay", exchange: "HNX", segment: "pharma", is_mvp: false },
  { ticker: "LDP", company_name: "Cong ty Co phan Duoc Lam Dong - Ladophar", exchange: "HNX", segment: "pharma", is_mvp: false },
  { ticker: "PPP", company_name: "Cong ty Co phan Duoc pham Phong Phu", exchange: "HNX", segment: "pharma", is_mvp: false },
  { ticker: "DP3", company_name: "Cong ty Co phan Duoc pham Trung uong 3", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DP1", company_name: "Cong ty Co phan Duoc pham Trung uong CPC1", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "TW3", company_name: "Cong ty Co phan Duoc - Trang thiet bi Y te Da Nang", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "MED", company_name: "Cong ty Co phan Duoc Trung uong Mediplantex", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "PMC", company_name: "Cong ty Co phan Duoc pham Duoc lieu Pharmedic", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "AMV", company_name: "Cong ty Co phan San xuat Kinh doanh Duoc va Trang thiet bi Y te Viet My", exchange: "HNX", segment: "medical_equipment", is_mvp: false },
  { ticker: "YTC", company_name: "Cong ty Co phan Xuat nhap khau Y te Thanh pho Ho Chi Minh", exchange: "UPCOM", segment: "medical_distribution", is_mvp: false },
  { ticker: "VHE", company_name: "Cong ty Co phan Duoc lieu Viet Nam", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "VDP", company_name: "Cong ty Co phan Duoc pham Trung uong Vidipha", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DCL", company_name: "Cong ty Co phan Duoc pham Cuu Long", exchange: "HOSE", segment: "pharma", is_mvp: false },
  { ticker: "SPM", company_name: "Cong ty Co phan S.P.M", exchange: "HOSE", segment: "pharma", is_mvp: false },
  { ticker: "VMD", company_name: "Cong ty Co phan Y Duoc pham Vimedimex", exchange: "HNX", segment: "pharma", is_mvp: false },
  { ticker: "BVP", company_name: "Cong ty Co phan Duoc pham Binh Viet", exchange: "HNX", segment: "pharma", is_mvp: false },
  { ticker: "HBH", company_name: "Cong ty Co phan Chuoi Nha thuoc An Khang", exchange: "HOSE", segment: "medical_distribution", is_mvp: false },
  { ticker: "DNM", company_name: "Cong ty Co phan Dieu Duong Minh Hai", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DBT", company_name: "Cong ty Co phan Duoc pham Trung Viet", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DPP", company_name: "Cong ty Co phan Duoc pham Phuc Thanh", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DRP", company_name: "Cong ty Co phan Duoc Rarapharm", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "T32", company_name: "Cong ty Co phan Y te Ha Tay", exchange: "UPCOM", segment: "healthcare_services", is_mvp: false },
  { ticker: "DTP", company_name: "Cong ty Co phan Duoc Tay Ninh", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "VMC", company_name: "Cong ty Co phan Y Duoc Viet Nam", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "NDT", company_name: "Cong ty Co phan Benh vien Da khoa tinh Ninh Binh", exchange: "UPCOM", segment: "healthcare_services", is_mvp: false },
  { ticker: "P29", company_name: "Cong ty Co phan Duoc pham Trung uong 29", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DDS", company_name: "Cong ty Co phan Diagnostics", exchange: "UPCOM", segment: "medical_equipment", is_mvp: false },
  { ticker: "BID", company_name: "Cong ty Co phan Duoc Binh Duong", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "PDT", company_name: "Cong ty Co phan Duoc pham Dong Thap", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "BCR", company_name: "Cong ty Co phan Bio-Pharmachemie", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "VNP", company_name: "Cong ty Co phan Duoc Viet Nhon", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "YT1", company_name: "Cong ty Co phan Duoc pham Y te 1", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "CPC", company_name: "Cong ty Co phan Duoc pham CPC1 Ha Noi", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "HDA", company_name: "Cong ty Co phan Duoc Ha Dong", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "TMP", company_name: "Cong ty Co phan Duoc pham Tam Phuc", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DRG", company_name: "Cong ty Co phan Duoc Re Giang", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "LNT", company_name: "Cong ty Co phan Duoc Lien", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "HGP", company_name: "Cong ty Co phan Duoc pham Hung Gia", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "PVD", company_name: "Cong ty Co phan Duoc pham Viet Duc", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DGW", company_name: "Cong ty Co phan The gioi So", exchange: "HOSE", segment: "medical_distribution", is_mvp: false },
  { ticker: "CON", company_name: "Cong ty Co phan Duoc pham Con Khi", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "TNT", company_name: "Cong ty Co phan Duoc pham Tan Nhon Tay", exchange: "UPCOM", segment: "pharma", is_mvp: false },
];

export function segmentCounts(): Record<string, number> {
  return UNIVERSE.reduce<Record<string, number>>((acc, t) => {
    acc[t.segment] = (acc[t.segment] ?? 0) + 1;
    return acc;
  }, {});
}
