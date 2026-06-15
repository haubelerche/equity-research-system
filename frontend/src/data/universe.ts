export interface UniverseTicker {
  ticker: string;
  company_name: string;
  exchange: string;
  segment: "pharma" | "healthcare_services" | "medical_equipment" | "medical_distribution";
  is_mvp: boolean;
}

export const UNIVERSE: UniverseTicker[] = [
  { ticker: "DHG", company_name: "Công ty Cổ phần Dược Hậu Giang", exchange: "HOSE", segment: "pharma", is_mvp: true },
  { ticker: "IMP", company_name: "Công ty Cổ phần Dược phẩm Imexpharm", exchange: "HOSE", segment: "pharma", is_mvp: true },
  { ticker: "DMC", company_name: "Công ty Cổ phần Xuất nhập khẩu Y tế Domesco", exchange: "HOSE", segment: "pharma", is_mvp: true },
  { ticker: "TRA", company_name: "Công ty Cổ phần Traphaco", exchange: "HOSE", segment: "pharma", is_mvp: true },
  { ticker: "DBD", company_name: "Công ty Cổ phần Dược - Trang thiết bị Y tế Bình Định", exchange: "HOSE", segment: "pharma", is_mvp: true },
  { ticker: "OPC", company_name: "Công ty Cổ phần Dược phẩm OPC", exchange: "HOSE", segment: "pharma", is_mvp: false },
  { ticker: "MKP", company_name: "Công ty Cổ phần Hóa - Dược phẩm Mekophar", exchange: "HOSE", segment: "pharma", is_mvp: false },
  { ticker: "TNH", company_name: "Công ty Cổ phần Bệnh viện Quốc tế Thái Nguyên", exchange: "HOSE", segment: "healthcare_services", is_mvp: false },
  { ticker: "JVC", company_name: "Công ty Cổ phần Thiết bị Y tế Việt Nhật", exchange: "HOSE", segment: "medical_equipment", is_mvp: false },
  { ticker: "DVN", company_name: "Tổng Công ty Dược Việt Nam - CTCP", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DHT", company_name: "Công ty Cổ phần Dược phẩm Hà Tây", exchange: "HNX", segment: "pharma", is_mvp: false },
  { ticker: "LDP", company_name: "Công ty Cổ phần Dược Lâm Đồng - Ladophar", exchange: "HNX", segment: "pharma", is_mvp: false },
  { ticker: "PPP", company_name: "Công ty Cổ phần Dược phẩm Phong Phú", exchange: "HNX", segment: "pharma", is_mvp: false },
  { ticker: "DP3", company_name: "Công ty Cổ phần Dược phẩm Trung ương 3", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DP1", company_name: "Công ty Cổ phần Dược phẩm Trung ương CPC1", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "TW3", company_name: "Công ty Cổ phần Dược - Trang thiết bị Y tế Đà Nẵng", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "MED", company_name: "Công ty Cổ phần Dược Trung ương Mediplantex", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "PMC", company_name: "Công ty Cổ phần Dược phẩm Dược liệu Pharmedic", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "AMV", company_name: "Công ty Cổ phần Sản xuất Kinh doanh Dược và Trang thiết bị Y tế Việt Mỹ", exchange: "HNX", segment: "medical_equipment", is_mvp: false },
  { ticker: "YTC", company_name: "Công ty Cổ phần Xuất nhập khẩu Y tế Thành phố Hồ Chí Minh", exchange: "UPCOM", segment: "medical_distribution", is_mvp: false },
  { ticker: "VHE", company_name: "Công ty Cổ phần Dược liệu Việt Nam", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "VDP", company_name: "Công ty Cổ phần Dược phẩm Trung ương Vidipha", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DCL", company_name: "Công ty Cổ phần Dược phẩm Cửu Long", exchange: "HOSE", segment: "pharma", is_mvp: false },
  { ticker: "SPM", company_name: "Công ty Cổ phần S.P.M", exchange: "HOSE", segment: "pharma", is_mvp: false },
  { ticker: "VMD", company_name: "Công ty Cổ phần Y Dược phẩm Vimedimex", exchange: "HNX", segment: "pharma", is_mvp: false },
  { ticker: "HBH", company_name: "Công ty Cổ phần Chuỗi Nhà thuốc An Khang", exchange: "HOSE", segment: "medical_distribution", is_mvp: false },
  { ticker: "DNM", company_name: "Công ty Cổ phần Điều dưỡng Minh Hải", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DBT", company_name: "Công ty Cổ phần Dược phẩm Trung Việt", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DPP", company_name: "Công ty Cổ phần Dược phẩm Phúc Thành", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DTP", company_name: "Công ty Cổ phần Dược Tây Ninh", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "VMC", company_name: "Công ty Cổ phần Y Dược Việt Nam", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "NDT", company_name: "Công ty Cổ phần Bệnh viện Đa khoa tỉnh Ninh Bình", exchange: "UPCOM", segment: "healthcare_services", is_mvp: false },
  { ticker: "BID", company_name: "Công ty Cổ phần Dược Bình Dương", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "BCR", company_name: "Công ty Cổ phần Bio-Pharmachemie", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "VNP", company_name: "Công ty Cổ phần Dược Việt Nhơn", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "CPC", company_name: "Công ty Cổ phần Dược phẩm CPC1 Hà Nội", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "HDA", company_name: "Công ty Cổ phần Dược Hà Đông", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "TMP", company_name: "Công ty Cổ phần Dược phẩm Tâm Phúc", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DRG", company_name: "Công ty Cổ phần Dược Rế Giang", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "PVD", company_name: "Công ty Cổ phần Dược phẩm Việt Đức", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DGW", company_name: "Công ty Cổ phần Thế Giới Số", exchange: "HOSE", segment: "medical_distribution", is_mvp: false },
  { ticker: "TNT", company_name: "Công ty Cổ phần Dược phẩm Tân Nhơn Tây", exchange: "UPCOM", segment: "pharma", is_mvp: false },
];

export function segmentCounts(): Record<string, number> {
  return UNIVERSE.reduce<Record<string, number>>((acc, t) => {
    acc[t.segment] = (acc[t.segment] ?? 0) + 1;
    return acc;
  }, {});
}
