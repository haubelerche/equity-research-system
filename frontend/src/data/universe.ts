export type UniverseSegment =
  | "pharma"
  | "healthcare_services"
  | "medical_equipment"
  | "medical_distribution"
  | "vaccine_biologic"
  | "pharma_distribution";

export interface UniverseTicker {
  ticker: string;
  company_name: string;
  exchange: string;
  segment: UniverseSegment;
  is_mvp: boolean;
}

export const UNIVERSE: UniverseTicker[] = [
  { ticker: "DHG", company_name: "Cong ty Co phan Duoc Hau Giang", exchange: "HOSE", segment: "pharma", is_mvp: true },
  { ticker: "IMP", company_name: "Cong ty Co phan Duoc pham Imexpharm", exchange: "HOSE", segment: "pharma", is_mvp: true },
  { ticker: "DMC", company_name: "Cong ty Co phan Xuat nhap khau Y te Domesco", exchange: "HOSE", segment: "pharma", is_mvp: true },
  { ticker: "TRA", company_name: "Cong ty Co phan Traphaco", exchange: "HOSE", segment: "pharma", is_mvp: true },
  { ticker: "DBD", company_name: "Cong ty Co phan Duoc - Trang thiet bi Y te Binh Dinh", exchange: "HOSE", segment: "pharma", is_mvp: true },
  { ticker: "MKP", company_name: "Cong ty Co phan Hoa - Duoc pham Mekophar", exchange: "HOSE", segment: "pharma", is_mvp: false },
  { ticker: "PPP", company_name: "Cong ty Co phan Duoc pham Phong Phu", exchange: "HNX", segment: "pharma", is_mvp: false },
  { ticker: "DP3", company_name: "Cong ty Co phan Duoc pham Trung uong 3", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "PMC", company_name: "Cong ty Co phan Duoc pham Duoc lieu Pharmedic", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "VDP", company_name: "Cong ty Co phan Duoc pham Trung uong Vidipha", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "SPM", company_name: "Cong ty Co phan S.P.M", exchange: "HOSE", segment: "pharma", is_mvp: false },
  { ticker: "VMD", company_name: "Cong ty Co phan Y Duoc pham Vimedimex", exchange: "HNX", segment: "pharma", is_mvp: false },
  { ticker: "DTP", company_name: "Cong ty Co phan Duoc pham CPC1 Ha Noi", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "BIO", company_name: "Cong ty Co phan Vac xin va Sinh pham Nha Trang", exchange: "UPCOM", segment: "vaccine_biologic", is_mvp: false },
  { ticker: "CNC", company_name: "Cong ty Co phan Cong nghe Cao Traphaco", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DBM", company_name: "Cong ty Co phan Duoc - Vat tu Y te Dak Lak", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DHN", company_name: "Cong ty Co phan Duoc pham Ha Noi", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DTG", company_name: "Cong ty Co phan Duoc pham Tipharco", exchange: "HNX", segment: "pharma", is_mvp: false },
  { ticker: "NDC", company_name: "Cong ty Co phan Nam Duoc", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DPH", company_name: "CTCP Duoc pham Hai Phong", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "OPC", company_name: "CTCP Duoc pham OPC", exchange: "HOSE", segment: "pharma", is_mvp: false },
  { ticker: "TNH", company_name: "Cong ty Co phan Benh vien Quoc te Thai Nguyen", exchange: "HOSE", segment: "healthcare_services", is_mvp: false },
  { ticker: "JVC", company_name: "Cong ty Co phan Thiet bi Y te Viet Nhat", exchange: "HOSE", segment: "medical_equipment", is_mvp: false },
  { ticker: "DVN", company_name: "Tong Cong ty Duoc Viet Nam - CTCP", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DHT", company_name: "Cong ty Co phan Duoc pham Ha Tay", exchange: "HNX", segment: "pharma", is_mvp: false },
  { ticker: "LDP", company_name: "Cong ty Co phan Duoc Lam Dong - Ladophar", exchange: "HNX", segment: "pharma", is_mvp: false },
  { ticker: "DP1", company_name: "Cong ty Co phan Duoc pham Trung uong CPC1", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "TW3", company_name: "Cong ty Co phan Duoc Trung uong 3", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "MED", company_name: "Cong ty Co phan Duoc Trung uong Mediplantex", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "AMV", company_name: "Cong ty Co phan San xuat Kinh doanh Duoc va Trang thiet bi Y te Viet My", exchange: "HNX", segment: "medical_equipment", is_mvp: false },
  { ticker: "YTC", company_name: "Cong ty Co phan Xuat nhap khau Y te Thanh pho Ho Chi Minh", exchange: "UPCOM", segment: "medical_distribution", is_mvp: false },
  { ticker: "VHE", company_name: "Cong ty Co phan Duoc lieu Viet Nam", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DCL", company_name: "Cong ty Co phan Duoc pham Cuu Long", exchange: "HOSE", segment: "pharma", is_mvp: false },
  { ticker: "DNM", company_name: "Tong Cong ty co phan Y te Danameco", exchange: "UPCOM", segment: "medical_distribution", is_mvp: false },
  { ticker: "DBT", company_name: "Cong ty Co phan Duoc pham Ben Tre", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DPP", company_name: "Cong ty Co phan Duoc Dong Nai", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "AMP", company_name: "Cong ty Co phan Armephaco", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "BCP", company_name: "Cong ty Co phan Duoc Enlie", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "CDP", company_name: "Cong ty Co phan Duoc pham Trung uong Codupha", exchange: "UPCOM", segment: "pharma_distribution", is_mvp: false },
  { ticker: "DAN", company_name: "Cong ty Co phan Duoc Danapha", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DDN", company_name: "Cong ty Co phan Duoc va Thiet bi Y te Da Nang", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DP2", company_name: "Cong ty Co phan Duoc pham Trung uong 2", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "HDP", company_name: "Cong ty Co phan Duoc Ha Tinh", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "MTP", company_name: "Cong ty Co phan Duoc Medipharco", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DHD", company_name: "CTCP Duoc Vat tu Y te Hai Duong", exchange: "UPCOM", segment: "pharma", is_mvp: false },
];

export function segmentCounts(): Record<UniverseSegment, number> {
  return UNIVERSE.reduce(
    (counts, item) => ({
      ...counts,
      [item.segment]: counts[item.segment] + 1,
    }),
    {
      pharma: 0,
      healthcare_services: 0,
      medical_equipment: 0,
      medical_distribution: 0,
      vaccine_biologic: 0,
      pharma_distribution: 0,
    },
  );
}
