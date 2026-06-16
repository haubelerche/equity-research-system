export interface UniverseTicker {
  ticker: string;
  company_name: string;
  exchange: string;
  segment: "pharma" | "healthcare_services" | "medical_equipment" | "medical_distribution";
  is_mvp: boolean;
}

export const UNIVERSE: UniverseTicker[] = [
  { ticker: "DHG", company_name: "C�ng ty C? ph?n Du?c H?u Giang", exchange: "HOSE", segment: "pharma", is_mvp: true },
  { ticker: "IMP", company_name: "C�ng ty C? ph?n Du?c ph?m Imexpharm", exchange: "HOSE", segment: "pharma", is_mvp: true },
  { ticker: "DMC", company_name: "C�ng ty C? ph?n Xu?t nh?p kh?u Y t? Domesco", exchange: "HOSE", segment: "pharma", is_mvp: true },
  { ticker: "TRA", company_name: "C�ng ty C? ph?n Traphaco", exchange: "HOSE", segment: "pharma", is_mvp: true },
  { ticker: "DBD", company_name: "C�ng ty C? ph?n Du?c - Trang thi?t b? Y t? B�nh �?nh", exchange: "HOSE", segment: "pharma", is_mvp: true },
  { ticker: "OPC", company_name: "C�ng ty C? ph?n Du?c ph?m OPC", exchange: "HOSE", segment: "pharma", is_mvp: false },
  { ticker: "MKP", company_name: "C�ng ty C? ph?n H�a - Du?c ph?m Mekophar", exchange: "HOSE", segment: "pharma", is_mvp: false },
  { ticker: "TNH", company_name: "C�ng ty C? ph?n B?nh vi?n Qu?c t? Th�i Nguy�n", exchange: "HOSE", segment: "healthcare_services", is_mvp: false },
  { ticker: "JVC", company_name: "C�ng ty C? ph?n Thi?t b? Y t? Vi?t Nh?t", exchange: "HOSE", segment: "medical_equipment", is_mvp: false },
  { ticker: "DVN", company_name: "T?ng C�ng ty Du?c Vi?t Nam - CTCP", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DHT", company_name: "C�ng ty C? ph?n Du?c ph?m H� T�y", exchange: "HNX", segment: "pharma", is_mvp: false },
  { ticker: "LDP", company_name: "C�ng ty C? ph?n Du?c L�m �?ng - Ladophar", exchange: "HNX", segment: "pharma", is_mvp: false },
  { ticker: "PPP", company_name: "C�ng ty C? ph?n Du?c ph?m Phong Ph�", exchange: "HNX", segment: "pharma", is_mvp: false },
  { ticker: "DP3", company_name: "C�ng ty C? ph?n Du?c ph?m Trung uong 3", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DP1", company_name: "C�ng ty C? ph?n Du?c ph?m Trung uong CPC1", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "TW3", company_name: "C�ng ty C? ph?n Du?c - Trang thi?t b? Y t? �� N?ng", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "MED", company_name: "C�ng ty C? ph?n Du?c Trung uong Mediplantex", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "PMC", company_name: "C�ng ty C? ph?n Du?c ph?m Du?c li?u Pharmedic", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "AMV", company_name: "C�ng ty C? ph?n S?n xu?t Kinh doanh Du?c v� Trang thi?t b? Y t? Vi?t M?", exchange: "HNX", segment: "medical_equipment", is_mvp: false },
  { ticker: "YTC", company_name: "C�ng ty C? ph?n Xu?t nh?p kh?u Y t? Th�nh ph? H? Ch� Minh", exchange: "UPCOM", segment: "medical_distribution", is_mvp: false },
  { ticker: "VHE", company_name: "C�ng ty C? ph?n Du?c li?u Vi?t Nam", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "VDP", company_name: "C�ng ty C? ph?n Du?c ph?m Trung uong Vidipha", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DCL", company_name: "C�ng ty C? ph?n Du?c ph?m C?u Long", exchange: "HOSE", segment: "pharma", is_mvp: false },
  { ticker: "SPM", company_name: "C�ng ty C? ph?n S.P.M", exchange: "HOSE", segment: "pharma", is_mvp: false },
  { ticker: "VMD", company_name: "C�ng ty C? ph?n Y Du?c ph?m Vimedimex", exchange: "HNX", segment: "pharma", is_mvp: false },
  { ticker: "HBH", company_name: "C�ng ty C? ph?n Chu?i Nh� thu?c An Khang", exchange: "HOSE", segment: "medical_distribution", is_mvp: false },
  { ticker: "DNM", company_name: "C�ng ty C? ph?n �i?u du?ng Minh H?i", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DBT", company_name: "C�ng ty C? ph?n Du?c ph?m Trung Vi?t", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DPP", company_name: "C�ng ty C? ph?n Du?c ph?m Ph�c Th�nh", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DTP", company_name: "C�ng ty C? ph?n Du?c T�y Ninh", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "VMC", company_name: "C�ng ty C? ph?n Y Du?c Vi?t Nam", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "NDT", company_name: "C�ng ty C? ph?n B?nh vi?n �a khoa t?nh Ninh B�nh", exchange: "UPCOM", segment: "healthcare_services", is_mvp: false },
  { ticker: "BID", company_name: "C�ng ty C? ph?n Du?c B�nh Duong", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "BCR", company_name: "C�ng ty C? ph?n Bio-Pharmachemie", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "VNP", company_name: "C�ng ty C? ph?n Du?c Vi?t Nhon", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "CPC", company_name: "C�ng ty C? ph?n Du?c ph?m CPC1 H� N?i", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "HDA", company_name: "C�ng ty C? ph?n Du?c H� ��ng", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "TMP", company_name: "C�ng ty C? ph?n Du?c ph?m T�m Ph�c", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DRG", company_name: "C�ng ty C? ph?n Du?c R? Giang", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "PVD", company_name: "C�ng ty C? ph?n Du?c ph?m Vi?t �?c", exchange: "UPCOM", segment: "pharma", is_mvp: false },
  { ticker: "DGW", company_name: "C�ng ty C? ph?n Th? Gi?i S?", exchange: "HOSE", segment: "medical_distribution", is_mvp: false },
  { ticker: "TNT", company_name: "C�ng ty C? ph?n Du?c ph?m T�n Nhon T�y", exchange: "UPCOM", segment: "pharma", is_mvp: false },
];

export function segmentCounts(): Record<string, number> {
  return UNIVERSE.reduce<Record<string, number>>((acc, t) => {
    acc[t.segment] = (acc[t.segment] ?? 0) + 1;
    return acc;
  }, {});
}
